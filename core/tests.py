from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings

from .alerts import notify


class HealthzTests(TestCase):
    def setUp(self):
        self.client = Client()

    @patch('requests.get')
    @patch('core.celery.app.connection_for_write')
    def test_healthz_ok_quando_tudo_disponivel(self, mock_conn, mock_get):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_get.return_value = MagicMock(status_code=200)

        r = self.client.get('/healthz/')

        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['checks']['database'], 'ok')
        self.assertEqual(data['checks']['broker'], 'ok')

    @patch('core.celery.app.connection_for_write')
    def test_healthz_degraded_quando_broker_indisponivel(self, mock_conn):
        mock_conn.side_effect = ConnectionError('recusado')

        r = self.client.get('/healthz/')

        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()['status'], 'degraded')

    @patch('requests.get')
    @patch('core.celery.app.connection_for_write')
    def test_healthz_evolution_fora_nao_derruba_o_healthcheck(self, mock_conn, mock_get):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_get.side_effect = Exception('fora do ar')

        r = self.client.get('/healthz/')

        # banco e broker ok -> status geral continua 200, mesmo com a Evolution fora
        self.assertEqual(r.status_code, 200)
        self.assertIn('indisponível', r.json()['checks']['evolution'])


class AlertsTests(TestCase):
    def test_notify_sem_webhook_configurado_nao_faz_requisicao(self):
        with patch('requests.post') as mock_post:
            notify('teste_evento', detalhe='algo aconteceu')
        mock_post.assert_not_called()

    @override_settings(ALERT_WEBHOOK_URL='https://hooks.exemplo.com/alerta')
    @patch('requests.post')
    def test_notify_com_webhook_configurado_faz_post(self, mock_post):
        notify('teste_evento', detalhe='algo aconteceu', nivel='error', instance_id=42)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['evento'], 'teste_evento')
        self.assertEqual(kwargs['json']['instance_id'], 42)

    @override_settings(ALERT_WEBHOOK_URL='https://hooks.exemplo.com/alerta')
    @patch('requests.post')
    def test_notify_falha_no_webhook_nao_propaga_excecao(self, mock_post):
        mock_post.side_effect = Exception('timeout')
        notify('teste_evento')  # nao deve levantar


class QueueSizeTaskTests(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_check_queue_size_em_modo_eager_nao_faz_nada(self):
        from .tasks import check_queue_size

        self.assertEqual(check_queue_size(), 0)


class InterfaceEmPortuguesTests(TestCase):
    """RNF-09: 100% da interface em português. Rótulo de FK sem `verbose_name`
    herda o nome do campo em inglês ('Folder', 'Instance', 'Message')."""

    ROTULOS_EM_INGLES = {
        'folder',
        'owner',
        'instance',
        'contact',
        'group',
        'message',
        'stage',
        'pipeline',
        'lead',
        'trigger',
        'plan',
        'tag',
        'campaign',
        'created at',
        'updated at',
    }

    def test_nenhum_formulario_expoe_rotulo_em_ingles(self):
        import importlib
        import inspect

        from django import forms

        problemas = []
        apps_com_forms = (
            'accounts',
            'instances',
            'contacts',
            'library',
            'scripts',
            'campaigns',
            'triggers',
            'crm',
            'reports',
            'core',
        )
        for app in apps_com_forms:
            try:
                mod = importlib.import_module(f'{app}.forms')
            except ModuleNotFoundError:
                continue
            for nome, cls in inspect.getmembers(mod, inspect.isclass):
                if not issubclass(cls, forms.BaseForm) or cls.__module__ != mod.__name__:
                    continue
                try:
                    instancia = cls()
                except Exception:  # noqa: BLE001 — form que exige argumentos; ignorado nesta varredura
                    continue
                for campo, field in instancia.fields.items():
                    if str(field.label).strip().lower() in self.ROTULOS_EM_INGLES:
                        problemas.append(f'{app}.{nome}.{campo} -> "{field.label}"')

        self.assertEqual(problemas, [], f'Rótulos em inglês na interface: {problemas}')


class NormalizacaoDeTextoTests(TestCase):
    """core.text — comparação de palavras-chave sem acento e sem caixa."""

    def test_normalizar_remove_caixa_e_acento(self):
        from core.text import normalizar

        self.assertEqual(normalizar('Qual o PREÇO?'), 'qual o preco?')
        self.assertEqual(normalizar('Não'), 'nao')
        self.assertEqual(normalizar('AÇÚCAR'), 'acucar')
        self.assertEqual(normalizar(None), '')

    def test_separar_termos_remove_espacos_ao_redor(self):
        from core.text import separar_termos

        # regressão: sem o strip, ' sem interesse' (espaço depois da vírgula)
        # nunca casava com 'sem interesse'
        self.assertEqual(
            separar_termos('nao,  Não quero , sem interesse ,'),
            ['nao', 'nao quero', 'sem interesse'],
        )
        self.assertEqual(separar_termos(''), [])

    def test_contem_algum_ignora_acento_e_caixa(self):
        from core.text import contem_algum, separar_termos

        termos = separar_termos('nao, sem interesse')
        self.assertTrue(contem_algum('Não quero, obrigado', termos))
        self.assertTrue(contem_algum('NAO', termos))
        self.assertTrue(contem_algum('sem interesse por enquanto', termos))
        self.assertFalse(contem_algum('pode mandar!', termos))

    def test_contem_todos_exige_todas_as_palavras(self):
        from core.text import contem_todos, separar_termos

        termos = separar_termos('quero, grupo')
        self.assertTrue(contem_todos('quero entrar no grupo', termos))
        self.assertFalse(contem_todos('quero sim', termos))
        self.assertFalse(contem_todos('qualquer coisa', []))
