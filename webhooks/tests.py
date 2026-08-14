import json
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from core.factories import make_instance
from instances.models import Instance

from .models import WebhookEvent


@override_settings(EVOLUTION_WEBHOOK_SECRET='segredo-de-teste')
class WebhookReceptionTests(TestCase):
    def setUp(self):
        self.instance = make_instance(status=Instance.STATUS_DESCONECTADO)
        self.client = Client()
        self.url = f'/webhooks/evolution/{self.instance.evolution_instance_name}/?token=segredo-de-teste'

    def _post(self, payload, url=None):
        return self.client.post(url or self.url, data=json.dumps(payload), content_type='application/json')

    def test_token_invalido_retorna_403(self):
        url_errado = f'/webhooks/evolution/{self.instance.evolution_instance_name}/?token=errado'
        r = self._post({'event': 'connection.update', 'data': {}}, url=url_errado)
        self.assertEqual(r.status_code, 403)

    def test_instancia_inexistente_retorna_404(self):
        r = self._post({'event': 'connection.update'}, url='/webhooks/evolution/nao-existe/?token=segredo-de-teste')
        self.assertEqual(r.status_code, 404)

    def test_payload_invalido_retorna_400(self):
        r = self.client.post(self.url, data=b'nao e json', content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_connection_update_atualiza_status_da_instancia(self):
        r = self._post({'event': 'connection.update', 'data': {'state': 'open'}})
        self.assertEqual(r.status_code, 200)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, Instance.STATUS_CONECTADO)

    def test_evento_e_persistido(self):
        self._post({'event': 'connection.update', 'data': {'state': 'open'}})
        self.assertEqual(WebhookEvent.objects.filter(instance=self.instance).count(), 1)

    def test_idempotencia_por_message_id_nao_duplica_evento(self):
        payload = {
            'event': 'messages.upsert',
            'data': {
                'key': {'remoteJid': '5511911112222@s.whatsapp.net', 'fromMe': False, 'id': 'DUP-1'},
                'message': {'conversation': 'oi'},
            },
        }
        r1 = self._post(payload)
        r2 = self._post(payload)
        self.assertEqual(r1.json()['status'], 'recebido')
        self.assertEqual(r2.json()['status'], 'duplicado')
        self.assertEqual(WebhookEvent.objects.filter(message_id='DUP-1').count(), 1)

    def test_evento_desconhecido_e_marcado_processado_sem_erro(self):
        self._post({'event': 'algum.evento.novo', 'data': {}})
        evento = WebhookEvent.objects.filter(evento='algum.evento.novo').first()
        self.assertTrue(evento.processado)
        self.assertEqual(evento.erro, '')

    @patch('instances.evolution.EvolutionClient.send_text')
    def test_messages_upsert_de_fromme_e_ignorado(self, mock_send):
        self._post(
            {
                'event': 'messages.upsert',
                'data': {
                    'key': {'remoteJid': '5511911112222@s.whatsapp.net', 'fromMe': True, 'id': 'SELF-1'},
                    'message': {'conversation': 'oi'},
                },
            }
        )
        mock_send.assert_not_called()


class PurgeOldWebhookEventsTests(TestCase):
    def test_apaga_apenas_eventos_processados_e_antigos(self):
        from django.utils import timezone

        from .tasks import purge_old_webhook_events

        instance = make_instance()
        antigo_processado = WebhookEvent.objects.create(instance=instance, evento='x', payload={}, processado=True)
        WebhookEvent.objects.filter(pk=antigo_processado.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=45)
        )

        recente_processado = WebhookEvent.objects.create(instance=instance, evento='x', payload={}, processado=True)
        antigo_nao_processado = WebhookEvent.objects.create(instance=instance, evento='x', payload={}, processado=False)
        WebhookEvent.objects.filter(pk=antigo_nao_processado.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=45)
        )

        apagados = purge_old_webhook_events()

        self.assertEqual(apagados, 1)
        self.assertFalse(WebhookEvent.objects.filter(pk=antigo_processado.pk).exists())
        self.assertTrue(WebhookEvent.objects.filter(pk=recente_processado.pk).exists())
        self.assertTrue(WebhookEvent.objects.filter(pk=antigo_nao_processado.pk).exists())
