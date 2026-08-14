import io
from unittest.mock import patch

from django.test import TestCase

from core.factories import make_instance, make_user

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
