import io
from unittest.mock import patch

from django.test import TestCase

from core.factories import make_instance, make_user
from instances.evolution import TIMEOUT_LENTO, EvolutionClient, EvolutionUnavailable

from . import services
from .models import AdminActionLog, Contact, Group
from .utils import normalize_br_number


class NormalizeBrNumberTests(TestCase):
    def test_full_e164_mobile_ja_com_nono_digito(self):
        self.assertEqual(normalize_br_number('5511987654321'), '+5511987654321')

    def test_ddi_com_celular_formato_antigo_sem_nono_digito(self):
        # 55 + 11 + 87654321 (8 dígitos, prefixo 8 -> mobile) -> insere o 9
        self.assertEqual(normalize_br_number('551187654321'), '+5511987654321')

    def test_sem_ddi_com_nono_digito(self):
        self.assertEqual(normalize_br_number('11987654321'), '+5511987654321')

    def test_sem_ddi_formato_antigo(self):
        self.assertEqual(normalize_br_number('1187654321'), '+5511987654321')

    def test_fixo_mantem_oito_digitos(self):
        # DDD 11 + fixo comeca com 3 -> nao adiciona o 9
        self.assertEqual(normalize_br_number('551133224455'), '+551133224455')

    def test_com_mascara_e_espacos(self):
        self.assertEqual(normalize_br_number('+55 (11) 98765-4321'), '+5511987654321')

    def test_jid_do_whatsapp(self):
        self.assertEqual(normalize_br_number('5511987654321@s.whatsapp.net'), '+5511987654321')

    def test_jid_de_grupo_retorna_none(self):
        self.assertIsNone(normalize_br_number('123456789-987654@g.us'))

    def test_vazio_retorna_none(self):
        self.assertIsNone(normalize_br_number(''))
        self.assertIsNone(normalize_br_number(None))

    def test_numero_curto_invalido_retorna_none(self):
        self.assertIsNone(normalize_br_number('12345'))


class ImportExportCsvTests(TestCase):
    def setUp(self):
        self.owner = make_user(email='csv@teste.com')

    def test_import_csv_cria_contatos_validos_e_conta_invalidos_e_duplicados(self):
        csv_bytes = b'numero,nome\n11987654321,Fulano\n21998765432,Beltrano\n11987654321,Duplicado\n123,Invalido\n'
        resultado = services.import_csv(self.owner, io.BytesIO(csv_bytes))
        self.assertEqual(resultado, {'importados': 2, 'duplicados': 1, 'invalidos': 1})
        self.assertEqual(Contact.objects.filter(owner=self.owner).count(), 2)

    def test_import_csv_ignora_cabecalho(self):
        csv_bytes = b'numero,nome\n11987654321,Fulano\n'
        services.import_csv(self.owner, io.BytesIO(csv_bytes))
        self.assertEqual(Contact.objects.count(), 1)

    def test_export_csv_inclui_etiquetas(self):
        from .models import Tag

        contact = Contact.objects.create(owner=self.owner, numero_e164='+5511987654321', nome='Fulano')
        tag = Tag.objects.create(owner=self.owner, nome='vip')
        contact.tags.add(tag)

        csv_texto = services.export_csv(self.owner)
        self.assertIn('+5511987654321', csv_texto)
        self.assertIn('vip', csv_texto)


class DedupeContactsTests(TestCase):
    def setUp(self):
        self.owner = make_user(email='dedupe@teste.com')

    def test_dedupe_unifica_numeros_equivalentes_apos_normalizacao(self):
        # dois registros que normalizam para o mesmo numero (simulando dado sujo anterior à normalização,
        # já que o model não normaliza sozinho no save — só os services que passam por normalize_br_number)
        Contact.objects.create(owner=self.owner, numero_e164='551187654321', nome='')
        Contact.objects.create(owner=self.owner, numero_e164='+5511987654321', nome='Nome Certo')

        removidos = services.dedupe_contacts(self.owner)
        self.assertEqual(removidos, 1)
        restante = Contact.objects.get(owner=self.owner)
        self.assertEqual(restante.numero_e164, '+5511987654321')
        self.assertEqual(restante.nome, 'Nome Certo')


class GroupSyncAndExtractTests(TestCase):
    def setUp(self):
        self.owner = make_user(email='grp@teste.com')
        self.instance = make_instance(owner=self.owner)

    @patch('instances.evolution.EvolutionClient.fetch_all_groups')
    def test_sync_groups_cria_grupos(self, mock_fetch):
        mock_fetch.return_value = [{'id': '123@g.us', 'subject': 'Grupo Teste', 'size': 10}]
        grupos = services.sync_groups(self.instance)
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0].nome, 'Grupo Teste')
        self.assertEqual(grupos[0].membros_count, 10)

    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_extract_participants_exclui_o_proprio_bot(self, mock_participants):
        self.instance.numero = '+5511900000000'
        self.instance.save()
        group = Group.objects.create(instance=self.instance, nome='G', jid='g@g.us')

        mock_participants.return_value = [
            {'id': '5511911111111@s.whatsapp.net', 'name': 'Lead'},
            {'id': '5511900000000@s.whatsapp.net', 'name': 'Bot', 'admin': True},
        ]
        contatos = services.extract_participants(group)
        self.assertEqual(len(contatos), 1)
        group.refresh_from_db()
        self.assertTrue(group.bot_e_admin)

    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_extract_participants_usa_phonenumber_quando_o_id_e_lid(self, mock_participants):
        """A v2.3.7 manda `id` como LID; o telefone só existe em `phoneNumber`."""
        self.instance.numero = '+5548991896676'
        self.instance.save()
        group = Group.objects.create(instance=self.instance, nome='G', jid='g@g.us')

        mock_participants.return_value = {
            'participants': [
                {'id': '169397956132906@lid', 'phoneNumber': '554899072303@s.whatsapp.net', 'admin': None},
                {'id': '200871442956316@lid', 'phoneNumber': '554891896676@s.whatsapp.net', 'admin': 'admin'},
            ]
        }
        contatos = services.extract_participants(group)

        # 2 participantes, mas um deles e' o proprio bot -> 1 contato
        self.assertEqual(len(contatos), 1)
        self.assertEqual(contatos[0].numero_e164, '+5548999072303')
        group.refresh_from_db()
        self.assertTrue(group.bot_e_admin)

    def test_fetch_all_participants_usa_o_caminho_da_v2(self):
        # o caminho antigo (/group/fetchAllParticipants/{inst}/{jid}) da 404
        client = EvolutionClient()
        with patch.object(client, '_request') as mock_request:
            client.fetch_all_participants('inst', '123@g.us')
        args, kwargs = mock_request.call_args
        self.assertEqual(args[1], '/group/participants/inst')
        self.assertEqual(kwargs['params'], {'groupJid': '123@g.us'})


class DemoteSelfTests(TestCase):
    def setUp(self):
        self.owner = make_user(email='demote@teste.com')
        self.instance = make_instance(owner=self.owner, numero='+5511900000000')

    def test_demote_self_sem_bot_admin_nao_chama_api(self):
        group = Group.objects.create(instance=self.instance, nome='G', jid='g@g.us', bot_e_admin=False)
        with patch('instances.evolution.EvolutionClient.update_participant') as mock_update:
            resultado = services.demote_self(group)
        self.assertEqual(resultado, AdminActionLog.RESULTADO_NAO_ERA_ADMIN)
        mock_update.assert_not_called()

    @patch('instances.evolution.EvolutionClient.update_participant')
    def test_demote_self_sucesso_atualiza_flag(self, mock_update):
        mock_update.return_value = {}
        group = Group.objects.create(instance=self.instance, nome='G', jid='g@g.us', bot_e_admin=True)
        resultado = services.demote_self(group)
        self.assertEqual(resultado, AdminActionLog.RESULTADO_SUCESSO)
        group.refresh_from_db()
        self.assertFalse(group.bot_e_admin)


class SyncGroupsErroTests(TestCase):
    """Regressão: a sincronização falhava em silêncio e a view mostrava sucesso."""

    def setUp(self):
        self.owner = make_user(email='sync@teste.com')
        self.instance = make_instance(owner=self.owner)
        self.client.force_login(self.owner)

    @patch('instances.evolution.EvolutionClient.fetch_all_groups')
    def test_sync_groups_propaga_erro_em_vez_de_devolver_lista_vazia(self, mock_fetch):
        mock_fetch.side_effect = EvolutionUnavailable('read timeout')
        with self.assertRaises(EvolutionUnavailable):
            services.sync_groups(self.instance)

    @patch('instances.evolution.EvolutionClient.fetch_all_groups')
    def test_view_mostra_erro_quando_a_evolution_falha(self, mock_fetch):
        mock_fetch.side_effect = EvolutionUnavailable('read timeout')
        r = self.client.post(f'/contatos/grupos/sincronizar/{self.instance.pk}/', follow=True)
        avisos = [(m.level_tag, str(m)) for m in r.context['messages']]
        self.assertTrue(any(tag == 'error' for tag, _ in avisos), avisos)
        self.assertFalse(any('0 grupo(s) sincronizado(s)' in texto for _, texto in avisos), avisos)

    @patch('instances.evolution.EvolutionClient.fetch_all_groups')
    def test_view_reporta_o_total_real_quando_da_certo(self, mock_fetch):
        mock_fetch.return_value = [
            {'id': 'a@g.us', 'subject': 'Grupo A', 'size': 3},
            {'id': 'b@g.us', 'subject': 'Grupo B', 'size': 5},
        ]
        r = self.client.post(f'/contatos/grupos/sincronizar/{self.instance.pk}/', follow=True)
        textos = [str(m) for m in r.context['messages']]
        self.assertTrue(any('2 grupo(s) sincronizado(s)' in t for t in textos), textos)
        self.assertEqual(Group.objects.filter(instance=self.instance).count(), 2)

    def test_endpoints_de_grupo_usam_timeout_longo_e_sem_retry(self):
        # 10s (default) derrubava a sincronizacao: a Evolution real leva ~90s
        client = EvolutionClient()
        with patch.object(client, '_request') as mock_request:
            client.fetch_all_groups('inst')
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['timeout'], TIMEOUT_LENTO)
        self.assertFalse(kwargs['retry'])


class ExecutarEmBackgroundConcorrenciaTests(TestCase):
    """
    Regressão: a view usava `task.apply(...).get()`. O `.get()` consulta
    `celery._state._task_join_will_block`, que é uma flag GLOBAL de módulo
    (não thread-local) — no runserver multi-thread, outra requisição dentro
    de um apply() fazia esta estourar RuntimeError.
    """

    def setUp(self):
        self.owner = make_user(email='conc@teste.com')
        self.instance = make_instance(owner=self.owner)
        self.group = Group.objects.create(instance=self.instance, nome='G', jid='g@g.us')
        self.client.force_login(self.owner)

    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_extrair_funciona_com_outra_task_em_andamento_em_outra_thread(self, mock_participants):
        from celery._state import _set_task_join_will_block

        mock_participants.return_value = {
            'participants': [{'id': '1@lid', 'phoneNumber': '5511911110001@s.whatsapp.net'}]
        }

        # simula o estado deixado por uma task rodando em outra thread
        _set_task_join_will_block(True)
        try:
            r = self.client.post(f'/contatos/grupos/{self.group.pk}/extrair/', follow=True)
        finally:
            _set_task_join_will_block(False)

        self.assertEqual(r.status_code, 200)
        textos = [str(m) for m in r.context['messages']]
        self.assertTrue(any('1 participante(s) extraído(s)' in t for t in textos), textos)

    @patch('instances.evolution.EvolutionClient.fetch_all_groups')
    def test_sincronizar_tambem_sobrevive_a_flag_global_do_celery(self, mock_fetch):
        from celery._state import _set_task_join_will_block

        mock_fetch.return_value = [{'id': 'x@g.us', 'subject': 'Grupo X', 'size': 2}]

        _set_task_join_will_block(True)
        try:
            r = self.client.post(f'/contatos/grupos/sincronizar/{self.instance.pk}/', follow=True)
        finally:
            _set_task_join_will_block(False)

        textos = [str(m) for m in r.context['messages']]
        self.assertTrue(any('1 grupo(s) sincronizado(s)' in t for t in textos), textos)


class AdminsNuncaRecebemTests(TestCase):
    """Regra de produto: admin e superadmin de grupo nunca viram contato nem público."""

    def setUp(self):
        self.owner = make_user(email='adm@teste.com')
        self.instance = make_instance(owner=self.owner, numero='+5511900000000')
        self.group = Group.objects.create(instance=self.instance, nome='G', jid='g@g.us')

    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_admin_e_superadmin_nao_viram_contato(self, mock_participants):
        mock_participants.return_value = {
            'participants': [
                {'phoneNumber': '5511911110001@s.whatsapp.net', 'admin': None},
                {'phoneNumber': '5511911110002@s.whatsapp.net', 'admin': 'admin'},
                {'phoneNumber': '5511911110003@s.whatsapp.net', 'admin': 'superadmin'},
            ]
        }
        contatos = services.extract_participants(self.group)

        self.assertEqual([c.numero_e164 for c in contatos], ['+5511911110001'])
        numeros = set(Contact.objects.filter(owner=self.owner).values_list('numero_e164', flat=True))
        self.assertNotIn('+5511911110002', numeros)
        self.assertNotIn('+5511911110003', numeros)

    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_admin_extraido_antes_da_regra_e_desvinculado_do_grupo(self, mock_participants):
        from .models import GroupMember

        antigo = Contact.objects.create(owner=self.owner, numero_e164='+5511911110002', nome='Virou admin')
        GroupMember.objects.create(group=self.group, contact=antigo)

        mock_participants.return_value = {
            'participants': [
                {'phoneNumber': '5511911110001@s.whatsapp.net', 'admin': None},
                {'phoneNumber': '5511911110002@s.whatsapp.net', 'admin': 'admin'},
            ]
        }
        services.extract_participants(self.group)

        self.assertFalse(GroupMember.objects.filter(group=self.group, contact=antigo).exists())
        # o Contact continua existindo: pode ser membro comum de outro grupo
        self.assertTrue(Contact.objects.filter(pk=antigo.pk).exists())

    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_admin_nao_entra_no_publico_da_campanha(self, mock_participants):
        from campaigns.models import Campaign
        from campaigns.services import build_audience
        from core.factories import make_script

        mock_participants.return_value = {
            'participants': [
                {'phoneNumber': '5511911110001@s.whatsapp.net', 'admin': None},
                {'phoneNumber': '5511911110002@s.whatsapp.net', 'admin': 'superadmin'},
            ]
        }
        services.extract_participants(self.group)

        campaign = Campaign.objects.create(
            owner=self.owner,
            nome='C',
            instance=self.instance,
            script=make_script(owner=self.owner),
            status=Campaign.STATUS_RASCUNHO,
            antiduplicacao_dias=0,
        )
        campaign.grupos.add(self.group)
        build_audience(campaign)

        publico = set(campaign.campaign_contacts.values_list('contact__numero_e164', flat=True))
        self.assertEqual(publico, {'+5511911110001'})

    @patch('instances.evolution.EvolutionClient.fetch_all_participants')
    def test_bot_admin_ainda_e_detectado(self, mock_participants):
        mock_participants.return_value = {
            'participants': [
                {'phoneNumber': '5511900000000@s.whatsapp.net', 'admin': 'admin'},
                {'phoneNumber': '5511911110001@s.whatsapp.net', 'admin': None},
            ]
        }
        services.extract_participants(self.group)
        self.group.refresh_from_db()
        self.assertTrue(self.group.bot_e_admin)


class ContactDeleteViewTests(TestCase):
    def setUp(self):
        self.owner = make_user(email='del@teste.com')
        self.outro = make_user(email='outro-del@teste.com')
        self.contact = Contact.objects.create(owner=self.owner, numero_e164='+5511911110001', nome='Fulano')
        self.client.force_login(self.owner)

    def test_listagem_mostra_o_link_de_remover(self):
        r = self.client.get('/contatos/')
        self.assertContains(r, f'/contatos/{self.contact.pk}/remover/')

    def test_remove_o_contato_e_avisa(self):
        r = self.client.post(f'/contatos/{self.contact.pk}/remover/', follow=True)
        self.assertFalse(Contact.objects.filter(pk=self.contact.pk).exists())
        textos = [str(m) for m in r.context['messages']]
        self.assertTrue(any('removido' in t for t in textos), textos)

    def test_nao_remove_contato_de_outro_usuario(self):
        alheio = Contact.objects.create(owner=self.outro, numero_e164='+5511911110002', nome='Alheio')
        r = self.client.post(f'/contatos/{alheio.pk}/remover/')
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Contact.objects.filter(pk=alheio.pk).exists())


class ExclusaoDeContatoNaoAmpliaGatilhoTests(TestCase):
    """
    Regressão: `Trigger.contato` é SET_NULL, então apagar o contato
    transformava um gatilho restrito a UMA pessoa em gatilho global,
    respondendo automaticamente para a base inteira.
    """

    def setUp(self):
        self.owner = make_user(email='trg-del@teste.com')
        self.instance = make_instance(owner=self.owner)
        self.alvo = Contact.objects.create(owner=self.owner, numero_e164='+5511911110001')
        self.outro = Contact.objects.create(owner=self.owner, numero_e164='+5511911110002')

    def _trigger(self):
        from triggers.models import Trigger

        return Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='So para o alvo', palavras_chave='oi', contato=self.alvo
        )

    def test_apagar_o_contato_desativa_o_gatilho_em_vez_de_globaliza_lo(self):
        from triggers.services import match_triggers

        trigger = self._trigger()
        self.assertIsNotNone(match_triggers(self.instance, self.alvo, 'oi'))
        self.assertIsNone(match_triggers(self.instance, self.outro, 'oi'))

        self.alvo.delete()

        trigger.refresh_from_db()
        self.assertFalse(trigger.ativo)
        self.assertIsNone(match_triggers(self.instance, self.outro, 'oi'))

    def test_dedupe_tambem_nao_globaliza_o_gatilho(self):
        # dedupe mantem o contato MAIS ANTIGO e apaga os demais; o gatilho
        # precisa apontar para o que vai ser apagado (o mais novo).
        from triggers.services import match_triggers

        Contact.objects.create(owner=self.owner, numero_e164='5511911110003', nome='Sobrevivente')
        apagado = Contact.objects.create(owner=self.owner, numero_e164='+5511911110003')
        from triggers.models import Trigger

        trigger = Trigger.objects.create(
            owner=self.owner, instance=self.instance, nome='T', palavras_chave='oi', contato=apagado
        )

        services.dedupe_contacts(self.owner)

        self.assertFalse(Contact.objects.filter(pk=apagado.pk).exists())

        trigger.refresh_from_db()
        self.assertFalse(trigger.ativo)
        self.assertIsNone(match_triggers(self.instance, self.outro, 'oi'))

    def test_gatilho_sem_restricao_de_contato_nao_e_afetado(self):
        from triggers.models import Trigger

        global_ = Trigger.objects.create(owner=self.owner, instance=self.instance, nome='Global', palavras_chave='oi')
        self.alvo.delete()
        global_.refresh_from_db()
        self.assertTrue(global_.ativo)

    def test_tela_de_confirmacao_avisa_o_que_sera_apagado(self):
        self.client.force_login(self.owner)
        r = self.client.get(f'/contatos/{self.alvo.pk}/remover/')
        self.assertContains(r, 'não pode ser desfeita')
        self.assertContains(r, 'opt-out')


class DemoteNaoTocaEmOutrosAdminsTests(TestCase):
    """
    Trava de comportamento: 'Remover admin do bot antes de disparar' rebaixa
    APENAS o próprio bot. O Sparzap nunca rebaixa admin nem superadmin de
    terceiros — admins são mantidos fora do público por `extract_participants`,
    não por mudança na administração do grupo.
    """

    def setUp(self):
        self.owner = make_user(email='demote-escopo@teste.com')
        self.instance = make_instance(owner=self.owner, numero='+5511900000000')
        self.group = Group.objects.create(instance=self.instance, nome='G', jid='g@g.us', bot_e_admin=True)

    @patch('instances.evolution.EvolutionClient.update_participant')
    def test_demote_envia_somente_o_jid_do_bot(self, mock_update):
        mock_update.return_value = {}
        services.demote_self(self.group)

        kwargs = mock_update.call_args.kwargs
        self.assertEqual(kwargs['action'], 'demote')
        self.assertEqual(kwargs['participants'], ['5511900000000@s.whatsapp.net'])

    @patch('instances.evolution.EvolutionClient.update_participant')
    def test_campanha_com_remover_admin_antes_so_rebaixa_o_bot(self, mock_update):
        from campaigns.models import Campaign
        from core.factories import make_script

        mock_update.return_value = {}
        campaign = Campaign.objects.create(
            owner=self.owner,
            nome='C',
            instance=self.instance,
            script=make_script(owner=self.owner),
            remover_admin_antes=True,
        )
        campaign.grupos.add(self.group)

        services.demote_self_for_campaign(campaign)

        self.assertEqual(mock_update.call_count, 1)
        self.assertEqual(mock_update.call_args.kwargs['participants'], ['5511900000000@s.whatsapp.net'])
