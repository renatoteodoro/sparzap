from unittest.mock import patch

from django.test import Client, TestCase

from core.factories import make_instance, make_user

from .models import Instance


class InstanceViewsTests(TestCase):
    def setUp(self):
        self.owner = make_user(email='inst@teste.com')
        self.client = Client()
        self.client.force_login(self.owner)

    def test_lista_exige_login(self):
        client_deslogado = Client()
        r = client_deslogado.get('/instancias/')
        self.assertEqual(r.status_code, 302)

    @patch('instances.evolution.EvolutionClient.set_webhook')
    @patch('instances.evolution.EvolutionClient.create_instance')
    def test_criar_instancia_via_form(self, mock_create, mock_webhook):
        mock_create.return_value = {}
        mock_webhook.return_value = {}
        r = self.client.post(
            '/instancias/nova/',
            {
                'nome': 'Vendas Teste',
                'evolution_instance_name': 'vendas-teste',
                'limite_diario': 30,
                'janela_inicio': '08:00',
                'janela_fim': '21:00',
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Instance.objects.filter(owner=self.owner, nome='Vendas Teste').exists())
        mock_create.assert_called_once()

    def test_usuario_nao_ve_instancia_de_outro(self):
        outro = make_user(email='outro@teste.com')
        make_instance(owner=outro, nome='DoOutro')
        r = self.client.get('/instancias/')
        self.assertNotIn(b'DoOutro', r.content)

    @patch('instances.evolution.EvolutionClient.connect')
    def test_tela_de_conexao_lida_com_erro_da_evolution_sem_quebrar(self, mock_connect):
        from instances.evolution import EvolutionUnavailable

        instance = make_instance(owner=self.owner)
        mock_connect.side_effect = EvolutionUnavailable('conexão recusada')
        r = self.client.get(f'/instancias/{instance.pk}/conectar/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('conexão recusada'.encode(), r.content)

    @patch('instances.evolution.EvolutionClient.connection_state')
    def test_refresh_status_atualiza_para_conectado(self, mock_state):
        instance = make_instance(owner=self.owner, status=Instance.STATUS_DESCONECTADO)
        mock_state.return_value = {'instance': {'state': 'open'}}
        r = self.client.post(f'/instancias/{instance.pk}/status/')
        self.assertEqual(r.status_code, 302)
        instance.refresh_from_db()
        self.assertEqual(instance.status, Instance.STATUS_CONECTADO)

    def test_desativar_instancia(self):
        instance = make_instance(owner=self.owner)
        r = self.client.post(f'/instancias/{instance.pk}/desativar/')
        self.assertEqual(r.status_code, 302)
        instance.refresh_from_db()
        self.assertFalse(instance.ativo)

    @patch('instances.evolution.EvolutionClient.connect')
    def test_qrcode_nao_duplica_prefixo_quando_evolution_ja_manda_data_uri(self, mock_connect):
        # A Evolution real (v2.3.7) retorna o campo "base64" já como data URI
        # completa ("data:image/png;base64,...."), não só o payload cru.
        # Se o view não normalizar isso, o <img src> fica com o prefixo
        # duplicado ("data:image/png;base64,data:image/png;base64,...") e o
        # navegador nunca renderiza a imagem — foi exatamente isso que
        # quebrou o QR na prática, contra a Evolution real.
        mock_connect.return_value = {'base64': 'data:image/png;base64,ABC123=='}
        instance = make_instance(owner=self.owner)

        r = self.client.get(f'/instancias/{instance.pk}/conectar/')

        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('src="data:image/png;base64,ABC123=="', html)
        self.assertNotIn('base64,data:image', html)

    @patch('instances.evolution.EvolutionClient.connect')
    def test_qrcode_funciona_tambem_se_evolution_mandar_so_o_payload_cru(self, mock_connect):
        mock_connect.return_value = {'base64': 'ABC123=='}
        instance = make_instance(owner=self.owner)

        r = self.client.get(f'/instancias/{instance.pk}/conectar/')

        html = r.content.decode()
        self.assertIn('src="data:image/png;base64,ABC123=="', html)


class RegistrarWebhooksCommandTests(TestCase):
    """
    O webhook fica gravado na Evolution com a URL de quando a instância foi
    criada. Trocar o endereço do Sparzap (dev <-> produção, ou domínio novo
    na VPS) não reescreve esse registro sozinho: a Evolution continua
    chamando o endereço antigo e as respostas somem sem erro nenhum.
    """

    def setUp(self):
        self.owner = make_user(email='webhooks-cmd@teste.com')

    def _rodar(self):
        from io import StringIO

        from django.core.management import call_command

        saida = StringIO()
        call_command('registrar_webhooks', stdout=saida, stderr=saida)
        return saida.getvalue()

    @patch('instances.evolution.EvolutionClient.set_webhook')
    def test_reescreve_o_webhook_de_todas_as_instancias(self, mock_set):
        make_instance(owner=self.owner, nome='Um', evolution_instance_name='um')
        make_instance(owner=self.owner, nome='Dois', evolution_instance_name='dois')

        self._rodar()

        self.assertEqual(mock_set.call_count, 2)
        registradas = {chamada.args[0] for chamada in mock_set.call_args_list}
        self.assertEqual(registradas, {'um', 'dois'})

    @patch('instances.evolution.EvolutionClient.set_webhook')
    def test_usa_a_url_base_e_o_token_do_settings(self, mock_set):
        make_instance(owner=self.owner, evolution_instance_name='minha')

        with self.settings(
            EVOLUTION_WEBHOOK_BASE_URL='http://exemplo.test',
            EVOLUTION_WEBHOOK_SECRET='segredo123',
        ):
            self._rodar()

        url = mock_set.call_args.args[1]
        self.assertEqual(url, 'http://exemplo.test/webhooks/evolution/minha/?token=segredo123')

    @patch('instances.evolution.EvolutionClient.set_webhook')
    def test_uma_instancia_com_erro_nao_impede_as_outras(self, mock_set):
        from instances.evolution import EvolutionError

        make_instance(owner=self.owner, nome='Quebrada', evolution_instance_name='quebrada')
        make_instance(owner=self.owner, nome='Boa', evolution_instance_name='boa')

        def falha_so_na_quebrada(nome, *args, **kwargs):
            if nome == 'quebrada':
                raise EvolutionError('falhou')

        mock_set.side_effect = falha_so_na_quebrada

        saida = self._rodar()

        self.assertEqual(mock_set.call_count, 2)
        self.assertIn('quebrada', saida)
