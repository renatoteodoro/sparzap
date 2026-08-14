import datetime
from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from antiblock.models import DailyLimit
from contacts import services as contacts_services
from contacts.models import AdminActionLog, Group
from instances.models import Instance
from library.models import Message
from scripts import services as scripts_services
from scripts.models import Script, ScriptRun, ScriptStep

from . import services as campaigns_services
from .models import Campaign, CampaignContact


class Video3FlowIntegrationTests(TestCase):
    """
    Valida o fluxo completo do vídeo 3 (PRD 9.2.6): extrai membros de um
    grupo alheio -> remove o próprio admin (auto-demote) -> dispara um
    script de 2 passos para o público do grupo -> aguarda resposta ->
    resposta com a palavra-chave avança para a mensagem com o link.
    """

    def setUp(self):
        self.owner = User.objects.create_user(email='v3@teste.com', password='x', nome='Dono')
        self.instance = Instance.objects.create(
            owner=self.owner,
            nome='I1',
            evolution_instance_name='i1',
            status=Instance.STATUS_CONECTADO,
            numero='+5511900000000',
            limite_diario=100,
            # janela cobrindo o dia inteiro: este teste nao e' sobre janela,
            # nao pode depender do horario real em que roda (ver Sprint 7/17)
            janela_inicio=datetime.time(0, 0),
            janela_fim=datetime.time(23, 59),
        )
        self.msg1 = Message.objects.create(
            owner=self.owner, titulo='Convite', tipo='texto', conteudo='Oi {{nome}}! Quer entrar no grupo {{grupo}}?'
        )
        self.msg2 = Message.objects.create(
            owner=self.owner, titulo='Link', tipo='texto', conteudo='Aqui está o link: {{link}}'
        )

        self.script = Script.objects.create(owner=self.owner, nome='Funil vídeo 3')
        self.step_msg1 = ScriptStep.objects.create(
            script=self.script, ordem=1, tipo=ScriptStep.TIPO_MENSAGEM, message=self.msg1
        )
        self.step_wait = ScriptStep.objects.create(
            script=self.script, ordem=2, tipo=ScriptStep.TIPO_AGUARDAR_RESPOSTA, timeout_h=48
        )
        self.step_cond = ScriptStep.objects.create(
            script=self.script, ordem=3, tipo=ScriptStep.TIPO_CONDICAO, condicao_contem='quero'
        )
        self.step_fallback = ScriptStep.objects.create(
            script=self.script, ordem=4, tipo=ScriptStep.TIPO_DELAY, delay_s=0
        )
        self.step_link = ScriptStep.objects.create(
            script=self.script, ordem=5, tipo=ScriptStep.TIPO_MENSAGEM, message=self.msg2
        )
        self.step_cond.proximo_passo = self.step_link
        self.step_cond.save()

    @patch('instances.evolution.EvolutionClient.send_text')
    @patch('instances.evolution.EvolutionClient.update_participant')
    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_fluxo_completo_grupo_ate_link_apos_resposta(self, mock_participants, mock_demote, mock_send_text):
        # 1) extração de participantes de um grupo alheio (bot é admin sem querer)
        mock_participants.return_value = [
            {'id': '5511911111111@s.whatsapp.net', 'name': 'Lead 1', 'admin': False},
            {'id': '5511900000000@s.whatsapp.net', 'name': 'Bot', 'admin': True},  # o proprio bot, admin
        ]
        grupo = Group.objects.create(instance=self.instance, nome='Grupo Concorrente', jid='555-1@g.us')
        contatos = contacts_services.extract_participants(grupo)
        # o proprio bot aparece na lista de participantes (e' admin sem querer),
        # mas nao deve virar Contact/lead do proprio grupo -> so sobra 1 lead real
        self.assertEqual(len(contatos), 1)
        grupo.refresh_from_db()
        self.assertTrue(grupo.bot_e_admin)

        # 2) campanha com o grupo como publico e auto-demote automatico
        campaign = Campaign.objects.create(
            owner=self.owner,
            nome='Convite Grupo Ofertas',
            instance=self.instance,
            script=self.script,
            remover_admin_antes=True,
            antiduplicacao_dias=30,
        )
        campaign.grupos.add(grupo)

        mock_demote.return_value = {}
        mock_send_text.return_value = {'key': {'id': 'MSG-V3-1'}}
        # Em modo eager (sem broker real), apply_async(countdown=...) roda na hora —
        # aqui isolamos o teste do timeout de 48h do mesmo jeito que scripts/tests.py faz,
        # para validar o caminho de "aguarda resposta de verdade" e nao o de timeout.
        with patch('scripts.tasks.check_timeout.apply_async'):
            campaigns_services.start_campaign(campaign)

        # 3) auto-demote executado antes do disparo
        grupo.refresh_from_db()
        self.assertFalse(grupo.bot_e_admin)
        self.assertTrue(
            AdminActionLog.objects.filter(
                group=grupo, modo=AdminActionLog.MODO_AUTOMATICO, resultado=AdminActionLog.RESULTADO_SUCESSO
            ).exists()
        )

        # 4) publico materializado com apenas o lead real (bot excluido)
        self.assertEqual(CampaignContact.objects.filter(campaign=campaign).count(), 1)

        lead = CampaignContact.objects.get(campaign=campaign, contact__numero_e164='+5511911111111')
        self.assertEqual(lead.status, CampaignContact.STATUS_ENVIADA)
        self.assertEqual(lead.origem_grupo, grupo)

        run = lead.script_run
        run.refresh_from_db()
        self.assertEqual(run.status, ScriptRun.STATUS_AGUARDANDO)
        self.assertEqual(run.passo_atual_id, self.step_wait.id)

        # a variavel {{grupo}} foi renderizada na msg1 (primeira chamada ao send_text)
        primeiro_envio = mock_send_text.call_args_list[0]
        self.assertIn('Grupo Concorrente', primeiro_envio.args[2])

        # 5) resposta do lead com a palavra-chave -> avanca para a mensagem com o link
        scripts_services.resume_waiting_steps(lead.contact, 'sim, eu quero!')
        run.refresh_from_db()
        self.assertEqual(run.status, ScriptRun.STATUS_CONCLUIDO)

        segundo_envio = mock_send_text.call_args_list[1]
        self.assertIn('link', segundo_envio.args[2].lower())

        # 6) todos os envios passaram pelo AntiBlock (contador diario incrementado)
        limite = DailyLimit.objects.get(instance=self.instance)
        self.assertEqual(limite.enviadas, 2)


class CampaignLifecycleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='lc@lc.com', password='x')
        self.instance = Instance.objects.create(
            owner=self.owner, nome='I', evolution_instance_name='i-lc', status=Instance.STATUS_CONECTADO
        )
        self.script = Script.objects.create(owner=self.owner, nome='S')
        self.campaign = Campaign.objects.create(owner=self.owner, nome='C', instance=self.instance, script=self.script)

    def test_pause_campaign(self):
        campaigns_services.pause_campaign(self.campaign)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.STATUS_PAUSADA)

    def test_cancel_campaign(self):
        campaigns_services.cancel_campaign(self.campaign)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.STATUS_CANCELADA)

    def test_resume_campaign_volta_para_em_andamento_e_redispara(self):
        campaigns_services.pause_campaign(self.campaign)
        campaigns_services.resume_campaign(self.campaign)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, Campaign.STATUS_EM_ANDAMENTO)

    def test_process_campaign_contact_ignora_se_campanha_nao_esta_ativa(self):
        contact = self._make_contact()
        cc = CampaignContact.objects.create(campaign=self.campaign, contact=contact)
        resultado = campaigns_services.process_campaign_contact(cc)
        self.assertEqual(resultado, 'campanha_nao_ativa')

    def test_update_delivery_status_sem_log_correspondente_nao_quebra(self):
        # nenhum DeliveryLog com esse message_id ainda -> apenas nao faz nada
        campaigns_services.update_delivery_status('inexistente-123', 'DELIVERED')

    def _make_contact(self):
        from contacts.models import Contact

        return Contact.objects.create(owner=self.owner, numero_e164='+5511900011122', nome='C')


class ProcessCampaignContactEagerModeTests(TestCase):
    """
    Reproduz o bug real encontrado testando a aplicação: em modo eager (dev
    sem broker real, CELERY_TASK_ALWAYS_EAGER=True), reagendar via
    apply_async(countdown=...) executa NA HORA e de forma síncrona. Se o
    motivo do bloqueio (ex.: limite diário atingido, fora da janela) não
    muda entre uma chamada e outra, isso recursava infinitamente até
    `RecursionError` — algo que um usuário real hitaria sozinho ao iniciar
    uma campanha fora do horário configurado, rodando o servidor de dev
    padrão (CELERY_TASK_ALWAYS_EAGER=True no .env.example).
    """

    def setUp(self):
        from contacts.models import Contact

        self.owner = User.objects.create_user(email='eager@teste.com', password='x')
        self.instance = Instance.objects.create(
            owner=self.owner,
            nome='I',
            evolution_instance_name='i-eager',
            status=Instance.STATUS_CONECTADO,
            limite_diario=0,  # bloqueado por limite diário, deterministico (não depende do relógio)
        )
        self.script = Script.objects.create(owner=self.owner, nome='S')
        self.campaign = Campaign.objects.create(
            owner=self.owner,
            nome='C',
            instance=self.instance,
            script=self.script,
            status=Campaign.STATUS_EM_ANDAMENTO,
        )
        self.contact = Contact.objects.create(owner=self.owner, numero_e164='+5511900033344', nome='Lead')
        self.cc = CampaignContact.objects.create(campaign=self.campaign, contact=self.contact)

    def test_bloqueado_em_modo_eager_nao_recursa_e_no_maximo_marca_pendente(self):
        # antes da correção, isto estourava RecursionError
        resultado = campaigns_services.process_campaign_contact(self.cc)
        self.assertEqual(resultado, 'aguardando_condicao')
        self.cc.refresh_from_db()
        self.assertEqual(self.cc.status, CampaignContact.STATUS_PENDENTE)


class AudienceFilterTests(TestCase):
    def setUp(self):
        from contacts.models import Contact

        self.owner = User.objects.create_user(email='af@af.com', password='x')
        self.instance = Instance.objects.create(owner=self.owner, nome='I', evolution_instance_name='i-af')
        self.script = Script.objects.create(owner=self.owner, nome='S')
        self.contact = Contact.objects.create(owner=self.owner, numero_e164='+5511900022233', nome='C')

    def test_filtro_nao_respondeu_exclui_quem_ja_respondeu_outra_campanha(self):
        campanha_antiga = Campaign.objects.create(
            owner=self.owner, nome='Antiga', instance=self.instance, script=self.script
        )
        CampaignContact.objects.create(
            campaign=campanha_antiga, contact=self.contact, status=CampaignContact.STATUS_RESPONDIDA
        )

        nova = Campaign.objects.create(
            owner=self.owner,
            nome='Nova',
            instance=self.instance,
            script=self.script,
            filtro_publico=Campaign.FILTRO_NAO_RESPONDEU,
        )
        resultado = campaigns_services._aplicar_filtro_publico(nova, {self.contact})
        self.assertEqual(resultado, set())

    def test_filtro_todos_nao_exclui_ninguem(self):
        campanha = Campaign.objects.create(owner=self.owner, nome='C', instance=self.instance, script=self.script)
        resultado = campaigns_services._aplicar_filtro_publico(campanha, {self.contact})
        self.assertEqual(resultado, {self.contact})

    def test_antiduplicacao_zero_dias_desativa_o_filtro(self):
        campanha = Campaign.objects.create(
            owner=self.owner,
            nome='SemAntidupe',
            instance=self.instance,
            script=self.script,
            antiduplicacao_dias=0,
        )
        resultado = campaigns_services._aplicar_antiduplicacao(campanha, {self.contact})
        self.assertEqual(resultado, {self.contact})


class FailureRateAlertTests(TestCase):
    def setUp(self):
        from contacts.models import Contact

        self.owner = User.objects.create_user(email='fr@fr.com', password='x')
        self.instance = Instance.objects.create(owner=self.owner, nome='I', evolution_instance_name='i-fr')
        self.script = Script.objects.create(owner=self.owner, nome='S')
        self.campaign = Campaign.objects.create(
            owner=self.owner,
            nome='C',
            instance=self.instance,
            script=self.script,
            status=Campaign.STATUS_EM_ANDAMENTO,
        )
        for i in range(10):
            contato = Contact.objects.create(owner=self.owner, numero_e164=f'+551190000{i:02d}', nome=f'C{i}')
            status = CampaignContact.STATUS_FALHA if i < 5 else CampaignContact.STATUS_ENVIADA
            CampaignContact.objects.create(campaign=self.campaign, contact=contato, status=status)

    @patch('core.alerts.notify')
    def test_alerta_disparado_quando_taxa_de_falha_alta(self, mock_notify):
        from .tasks import check_failure_rates

        alertadas = check_failure_rates()
        self.assertEqual(alertadas, 1)
        mock_notify.assert_called_once()
        self.assertEqual(mock_notify.call_args.args[0], 'campanha_taxa_falha_alta')

    @patch('core.alerts.notify')
    def test_sem_alerta_abaixo_do_minimo_de_amostra(self, mock_notify):
        CampaignContact.objects.filter(campaign=self.campaign).delete()
        from .tasks import check_failure_rates

        self.assertEqual(check_failure_rates(), 0)
        mock_notify.assert_not_called()


class RevalidarAdminsAntesDoDisparoTests(TestCase):
    """
    Norma do produto: administrador de grupo nunca recebe mensagem do Sparzap.
    `extract_participants` garante isso na extração; a opção da campanha
    revalida imediatamente antes do disparo, fechando a janela de quem virou
    admin DEPOIS de o grupo ter sido extraído.
    """

    def setUp(self):
        from contacts.models import Group, GroupMember
        from core.factories import make_contact, make_instance, make_script, make_user

        self.owner = make_user(email='reval@teste.com')
        self.instance = make_instance(owner=self.owner, numero='+5511900000000')
        self.group = Group.objects.create(instance=self.instance, nome='G', jid='g@g.us')

        # extraidos quando ainda eram membros comuns
        self.comum = make_contact(owner=self.owner, numero_e164='+5511911110001')
        self.virou_admin = make_contact(owner=self.owner, numero_e164='+5511911110002')
        GroupMember.objects.create(group=self.group, contact=self.comum)
        GroupMember.objects.create(group=self.group, contact=self.virou_admin)

        self.script = make_script(owner=self.owner)

    def _campanha(self, revalidar):
        campaign = Campaign.objects.create(
            owner=self.owner,
            nome='C',
            instance=self.instance,
            script=self.script,
            antiduplicacao_dias=0,
            remover_admin_antes=revalidar,
        )
        campaign.grupos.add(self.group)
        return campaign

    def _publico(self, campaign):
        return set(campaign.campaign_contacts.values_list('contact__numero_e164', flat=True))

    @patch('campaigns.tasks.dispatch_campaign.delay')
    @patch('instances.evolution.EvolutionClient.update_participant')
    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_com_a_opcao_marcada_o_admin_novo_fica_fora_do_publico(self, mock_part, mock_upd, mock_delay):
        mock_part.return_value = {
            'participants': [
                {'phoneNumber': '5511911110001@s.whatsapp.net', 'admin': None},
                {'phoneNumber': '5511911110002@s.whatsapp.net', 'admin': 'admin'},
            ]
        }
        campaign = self._campanha(revalidar=True)
        campaigns_services.start_campaign(campaign)

        self.assertEqual(self._publico(campaign), {'+5511911110001'})

    @patch('campaigns.tasks.dispatch_campaign.delay')
    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_sem_a_opcao_o_vinculo_velho_prevalece(self, mock_part, mock_delay):
        campaign = self._campanha(revalidar=False)
        campaigns_services.start_campaign(campaign)

        mock_part.assert_not_called()
        self.assertEqual(self._publico(campaign), {'+5511911110001', '+5511911110002'})

    @patch('campaigns.tasks.dispatch_campaign.delay')
    @patch('instances.evolution.EvolutionClient.update_participant')
    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_falha_na_evolution_nao_aborta_a_campanha(self, mock_part, mock_upd, mock_delay):
        from instances.evolution import EvolutionUnavailable

        mock_part.side_effect = EvolutionUnavailable('timeout')
        campaign = self._campanha(revalidar=True)
        campaigns_services.start_campaign(campaign)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.STATUS_EM_ANDAMENTO)
