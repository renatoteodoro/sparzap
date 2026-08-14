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
