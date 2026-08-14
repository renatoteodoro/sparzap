from django.test import TestCase

from accounts.models import User
from contacts.models import Contact

from . import services
from .models import ConversationMessage, Lead


class CrmServicesTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='crm@crm.com', password='x')
        self.contact = Contact.objects.create(owner=self.owner, numero_e164='+5511911112222', nome='Lead')

    def test_get_or_create_default_pipeline_cria_etapas_padrao(self):
        pipeline = services.get_or_create_default_pipeline(self.owner)
        nomes = list(pipeline.stages.order_by('ordem').values_list('nome', flat=True))
        self.assertEqual(nomes, services.ETAPAS_PADRAO)

    def test_get_or_create_default_pipeline_e_idempotente_por_owner(self):
        p1 = services.get_or_create_default_pipeline(self.owner)
        p2 = services.get_or_create_default_pipeline(self.owner)
        self.assertEqual(p1.id, p2.id)

    def test_get_or_create_lead_comeca_na_primeira_etapa(self):
        lead = services.get_or_create_lead(self.contact)
        self.assertEqual(lead.stage.nome, 'Novo')

    def test_move_stage_registra_nota_automatica(self):
        lead = services.get_or_create_lead(self.contact)
        interessado = lead.pipeline.stages.get(nome='Interessado')
        services.move_stage(lead, interessado, motivo='teste')
        lead.refresh_from_db()
        self.assertEqual(lead.stage, interessado)
        self.assertTrue(lead.notas.filter(automatica=True).exists())

    def test_move_stage_para_a_mesma_etapa_nao_duplica_nota(self):
        lead = services.get_or_create_lead(self.contact)
        services.move_stage(lead, lead.stage)
        self.assertEqual(lead.notas.count(), 0)

    def test_log_incoming_message_avanca_de_novo_para_respondeu(self):
        lead = services.log_incoming_message(self.contact, 'oi, tenho interesse')
        self.assertEqual(lead.stage.nome, 'Respondeu')
        self.assertEqual(lead.mensagens.count(), 1)
        self.assertEqual(lead.mensagens.first().direcao, ConversationMessage.DIRECAO_ENTRADA)

    def test_log_outgoing_message_avanca_de_novo_para_contatado(self):
        lead = services.log_outgoing_message(self.contact, 'Oi, tudo bem?')
        self.assertEqual(lead.stage.nome, 'Contatado')

    def test_log_incoming_nao_regride_etapa_avancada(self):
        lead = services.get_or_create_lead(self.contact)
        vendido = lead.pipeline.stages.get(nome='Vendido')
        services.move_stage(lead, vendido)
        services.log_incoming_message(self.contact, 'obrigado!')
        lead.refresh_from_db()
        self.assertEqual(lead.stage.nome, 'Vendido')

    def test_move_stage_by_name_cria_etapa_se_nao_existir(self):
        lead = services.move_stage_by_name(self.contact, 'Etapa Customizada')
        self.assertEqual(lead.stage.nome, 'Etapa Customizada')

    def test_stage_conversion_soma_100_por_cento(self):
        pipeline = services.get_or_create_default_pipeline(self.owner)
        services.get_or_create_lead(self.contact)
        outro_contato = Contact.objects.create(owner=self.owner, numero_e164='+5511922223333', nome='Outro')
        lead2 = services.get_or_create_lead(outro_contato)
        services.move_stage(lead2, pipeline.stages.get(nome='Vendido'))

        resultado = services.stage_conversion(pipeline)
        total_percentual = sum(r['percentual'] for r in resultado)
        self.assertAlmostEqual(total_percentual, 100.0, delta=0.1)

    def test_unique_lead_por_contato_e_pipeline(self):
        lead1 = services.get_or_create_lead(self.contact)
        lead2 = services.get_or_create_lead(self.contact)
        self.assertEqual(lead1.id, lead2.id)
        self.assertEqual(Lead.objects.filter(contact=self.contact).count(), 1)
