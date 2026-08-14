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
