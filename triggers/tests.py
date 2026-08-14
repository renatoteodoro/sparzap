import datetime
from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from contacts.models import Contact
from instances.models import Instance
from library.models import Message

from . import services
from .models import Trigger, TriggerLog


class TriggerEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='t@t.com', password='x')
        self.instance = Instance.objects.create(
            owner=self.owner,
            nome='I1',
            evolution_instance_name='i1',
            status=Instance.STATUS_CONECTADO,
            numero='+5511900000000',
            # janela cobrindo o dia inteiro: este teste nao e' sobre janela,
            # nao pode depender do horario real em que roda (ver Sprint 7/17)
            janela_inicio=datetime.time(0, 0),
            janela_fim=datetime.time(23, 59),
        )
        self.contact = Contact.objects.create(owner=self.owner, numero_e164='+5511911111111', nome='Lead')
        self.resposta = Message.objects.create(
            owner=self.owner, titulo='Auto', tipo='texto', conteudo='Oi {{nome}}, aqui está!'
        )

    def test_modo_ou_casa_com_qualquer_palavra(self):
        trigger = Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='T1', palavras_chave='quero, preço', modo=Trigger.MODO_OU
        )
        self.assertEqual(services.match_triggers(self.instance, self.contact, 'qual o preço?'), trigger)
        self.assertIsNone(services.match_triggers(self.instance, self.contact, 'oi tudo bem'))

    def test_modo_e_precisa_de_todas_as_palavras(self):
        trigger = Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='T2', palavras_chave='quero, grupo', modo=Trigger.MODO_E
        )
        self.assertIsNone(services.match_triggers(self.instance, self.contact, 'eu quero'))
        self.assertEqual(services.match_triggers(self.instance, self.contact, 'quero entrar no grupo'), trigger)

    def test_prioridade_menor_e_avaliada_primeiro(self):
        Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='Baixa', palavras_chave='quero', prioridade=200
        )
        alta = Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='Alta', palavras_chave='quero', prioridade=10
        )
        self.assertEqual(services.match_triggers(self.instance, self.contact, 'quero'), alta)

    def test_trigger_inativo_nao_casa(self):
        Trigger.objects.create(owner=self.owner, instance=self.instance, nome='T3', palavras_chave='quero', ativo=False)
        self.assertIsNone(services.match_triggers(self.instance, self.contact, 'quero'))

    def test_anti_loop_nao_repete_dentro_da_janela(self):
        trigger = Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='T4', palavras_chave='quero', limite_repeticao_minutos=60
        )
        TriggerLog.objects.create(trigger=trigger, contact=self.contact)
        self.assertIsNone(services.match_triggers(self.instance, self.contact, 'quero'))

    @patch('instances.evolution.EvolutionClient.send_text')
    def test_evaluate_triggers_responde_etiqueta_e_registra_log(self, mock_send):
        mock_send.return_value = {'key': {'id': 'T1'}}
        trigger = Trigger.objects.create(
            owner=self.owner,
            instance=self.instance,
            nome='T5',
            palavras_chave='quero',
            resposta=self.resposta,
            etiqueta_nome='interessado',
        )
        resultado = services.evaluate_triggers(self.instance, self.contact, 'eu quero muito')
        self.assertEqual(resultado, trigger)
        mock_send.assert_called_once()
        self.assertTrue(self.contact.tags.filter(nome='interessado').exists())
        log = TriggerLog.objects.get(trigger=trigger, contact=self.contact)
        self.assertIn('responder', log.acoes_executadas)
        self.assertIn('etiquetar', log.acoes_executadas)

    def test_escopo_por_contato_restringe_o_gatilho(self):
        outro_contato = Contact.objects.create(owner=self.owner, numero_e164='+5511922222222', nome='Outro')
        trigger = Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='T6', palavras_chave='quero', contato=self.contact
        )
        self.assertEqual(services.match_triggers(self.instance, self.contact, 'quero'), trigger)
        self.assertIsNone(services.match_triggers(self.instance, outro_contato, 'quero'))

    def test_gatilho_com_followup_agenda_mensagem(self):
        from django.utils import timezone

        from .models import ScheduledMsg

        Trigger.objects.create(
            owner=self.owner,
            instance=self.instance,
            nome='T7',
            palavras_chave='amanha',
            followup_mensagem=self.resposta,
            followup_apos_horas=24,
        )
        services.evaluate_triggers(self.instance, self.contact, 'me chama amanha')
        agendada = ScheduledMsg.objects.get(contact=self.contact)
        self.assertEqual(agendada.origem, ScheduledMsg.ORIGEM_GATILHO)
        self.assertGreater(agendada.data_hora, timezone.now() + timezone.timedelta(hours=23))


class ScheduledMsgTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='sm@sm.com', password='x')
        self.instance = Instance.objects.create(
            owner=self.owner,
            nome='I1',
            evolution_instance_name='i1',
            status=Instance.STATUS_CONECTADO,
            limite_diario=50,
            # janela cobrindo o dia inteiro: este teste nao e' sobre janela,
            # nao pode depender do horario real em que roda (ver Sprint 7/17)
            janela_inicio=datetime.time(0, 0),
            janela_fim=datetime.time(23, 59),
        )
        self.contact = Contact.objects.create(owner=self.owner, numero_e164='+5511933333333', nome='Lead')
        self.msg = Message.objects.create(
            owner=self.owner, titulo='Followup', tipo='texto', conteudo='Oi {{nome}}, tudo certo?'
        )

    @patch('instances.evolution.EvolutionClient.send_text')
    def test_dispatch_due_envia_apenas_as_vencidas(self, mock_send):
        from django.utils import timezone

        from . import services
        from .models import ScheduledMsg

        mock_send.return_value = {'key': {'id': 'F1'}}
        vencida = services.schedule_message(
            self.contact, self.instance, self.msg, timezone.now() - timezone.timedelta(minutes=5)
        )
        futura = services.schedule_message(
            self.contact, self.instance, self.msg, timezone.now() + timezone.timedelta(days=1)
        )

        total = services.dispatch_due_scheduled_messages()

        self.assertEqual(total, 1)
        vencida.refresh_from_db()
        futura.refresh_from_db()
        self.assertEqual(vencida.status, ScheduledMsg.STATUS_ENVIADA)
        self.assertEqual(futura.status, ScheduledMsg.STATUS_PENDENTE)
        mock_send.assert_called_once()

    def test_cancel_e_reschedule(self):
        from django.utils import timezone

        from . import services
        from .models import ScheduledMsg

        agendada = services.schedule_message(
            self.contact, self.instance, self.msg, timezone.now() + timezone.timedelta(days=1)
        )
        services.cancel_scheduled_message(agendada)
        agendada.refresh_from_db()
        self.assertEqual(agendada.status, ScheduledMsg.STATUS_CANCELADA)

        nova_data = timezone.now() + timezone.timedelta(days=2)
        services.reschedule_message(agendada, nova_data)
        agendada.refresh_from_db()
        self.assertEqual(agendada.status, ScheduledMsg.STATUS_PENDENTE)
        self.assertEqual(agendada.data_hora, nova_data)


class GatilhoIgnoraAcentoTests(TestCase):
    """Gatilho e condição de roteiro seguem a mesma regra (core.text)."""

    def setUp(self):
        self.owner = User.objects.create_user(email='ac@ac.com', password='x')
        self.instance = Instance.objects.create(
            owner=self.owner,
            nome='I1',
            evolution_instance_name='i1',
            status=Instance.STATUS_CONECTADO,
            janela_inicio=datetime.time(0, 0),
            janela_fim=datetime.time(23, 59),
        )
        self.contact = Contact.objects.create(owner=self.owner, numero_e164='+5511911111111')

    def test_palavra_com_acento_casa_com_texto_sem_acento(self):
        trigger = Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='T', palavras_chave='preço'
        )
        for texto in ('qual o preço?', 'qual o preco?', 'QUAL O PRECO'):
            self.assertEqual(services.match_triggers(self.instance, self.contact, texto), trigger, texto)

    def test_palavra_sem_acento_casa_com_texto_acentuado(self):
        trigger = Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='T', palavras_chave='nao quero'
        )
        self.assertEqual(services.match_triggers(self.instance, self.contact, 'Não quero'), trigger)

    def test_modo_e_tambem_ignora_acento(self):
        trigger = Trigger.objects.create(
            owner=self.owner,
            instance=self.instance,
            nome='T',
            palavras_chave='endereço, entrega',
            modo=Trigger.MODO_E,
        )
        self.assertEqual(
            services.match_triggers(self.instance, self.contact, 'qual o endereco de entrega?'), trigger
        )
