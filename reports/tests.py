from django.test import TestCase

from accounts.models import User
from campaigns.models import Campaign
from crm.models import Pipeline
from instances.models import Instance
from library.models import Message
from scripts.models import Script, ScriptStep
from triggers.models import Trigger

from . import backup


class BackupRoundTripTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='bk@bk.com', password='x')
        self.instance_origem = Instance.objects.create(
            owner=self.owner, nome='Origem', evolution_instance_name='origem'
        )
        self.instance_destino = Instance.objects.create(
            owner=self.owner, nome='Destino', evolution_instance_name='destino'
        )

        self.msg1 = Message.objects.create(owner=self.owner, titulo='Convite', tipo='texto', conteudo='Oi {{nome}}')
        self.msg2 = Message.objects.create(owner=self.owner, titulo='Link', tipo='texto', conteudo='Aqui: {{link}}')

        self.script = Script.objects.create(owner=self.owner, nome='Funil')
        ScriptStep.objects.create(script=self.script, ordem=1, tipo=ScriptStep.TIPO_MENSAGEM, message=self.msg1)
        ScriptStep.objects.create(script=self.script, ordem=2, tipo=ScriptStep.TIPO_AGUARDAR_RESPOSTA, timeout_h=48)
        cond = ScriptStep.objects.create(
            script=self.script, ordem=3, tipo=ScriptStep.TIPO_CONDICAO, condicao_contem='quero'
        )
        link_step = ScriptStep.objects.create(
            script=self.script, ordem=4, tipo=ScriptStep.TIPO_MENSAGEM, message=self.msg2
        )
        cond.proximo_passo = link_step
        cond.save()

        Trigger.objects.create(
            owner=self.owner, instance=self.instance_origem, nome='Gatilho1', palavras_chave='oi', resposta=self.msg1
        )
        Campaign.objects.create(owner=self.owner, nome='Camp1', instance=self.instance_origem, script=self.script)

    def test_export_contains_all_sections(self):
        dados = backup.export_config(self.owner)
        self.assertEqual(dados['schema_version'], backup.SCHEMA_VERSION)
        self.assertEqual(len(dados['mensagens']), 2)
        self.assertEqual(len(dados['scripts']), 1)
        self.assertEqual(len(dados['scripts'][0]['passos']), 4)
        self.assertEqual(len(dados['gatilhos']), 1)
        self.assertEqual(len(dados['campanhas']), 1)

    def test_export_selective_only_includes_requested_sections(self):
        dados = backup.export_config(self.owner, secoes=['mensagens'])
        self.assertIn('mensagens', dados)
        self.assertNotIn('scripts', dados)
        self.assertNotIn('gatilhos', dados)

    def test_import_recria_tudo_remapeado_para_outra_instancia(self):
        dados = backup.export_config(self.owner)

        # apaga tudo (simula importar num sparzap "vazio" para o mesmo owner, exceto os proprios dados de origem)
        Message.objects.all().delete()
        Script.objects.all().delete()
        Trigger.objects.all().delete()
        Campaign.objects.all().delete()

        relatorio = backup.import_config(self.owner, self.instance_destino, dados, conflito='ignorar')

        self.assertEqual(relatorio['criados'], 2 + 1 + 1 + 1)  # 2 msgs + 1 script + 1 gatilho + 1 campanha

        script_importado = Script.objects.get(owner=self.owner, nome='Funil')
        passos = list(script_importado.steps.order_by('ordem'))
        self.assertEqual(len(passos), 4)
        self.assertEqual(passos[2].proximo_passo_id, passos[3].id)  # condicao -> link, remapeado por ordem

        trigger_importado = Trigger.objects.get(owner=self.owner, nome='Gatilho1')
        self.assertEqual(trigger_importado.instance, self.instance_destino)
        self.assertEqual(trigger_importado.resposta.titulo, 'Convite')

        campanha_importada = Campaign.objects.get(owner=self.owner, nome='Camp1')
        self.assertEqual(campanha_importada.instance, self.instance_destino)
        self.assertEqual(campanha_importada.script, script_importado)

    def test_import_ignora_duplicado_por_nome(self):
        dados = backup.export_config(self.owner, secoes=['mensagens'])
        relatorio = backup.import_config(self.owner, self.instance_destino, dados, conflito='ignorar')
        self.assertEqual(relatorio['ignorados'], 2)
        self.assertEqual(relatorio['criados'], 0)
        self.assertEqual(Message.objects.filter(owner=self.owner, titulo='Convite').count(), 1)

    def test_import_renomeia_duplicado(self):
        dados = backup.export_config(self.owner, secoes=['mensagens'])
        backup.import_config(self.owner, self.instance_destino, dados, conflito='renomear')
        self.assertTrue(Message.objects.filter(owner=self.owner, titulo='Convite (importado)').exists())

    def test_validate_config_rejeita_arquivo_sem_schema_version(self):
        valido, erro = backup.validate_config({'foo': 'bar'})
        self.assertFalse(valido)

    def test_validate_config_rejeita_versao_futura(self):
        valido, erro = backup.validate_config({'schema_version': 999})
        self.assertFalse(valido)

    def test_import_pipelines(self):
        pipeline = Pipeline.objects.create(owner=self.owner, nome='CustomPipe')
        from crm.models import Stage

        Stage.objects.create(pipeline=pipeline, nome='Etapa1', ordem=0)

        dados = backup.export_config(self.owner, secoes=['pipelines'])
        Pipeline.objects.all().delete()

        relatorio = backup.import_config(self.owner, self.instance_destino, dados, conflito='ignorar')
        self.assertEqual(relatorio['criados'], 1)
        pipeline_importado = Pipeline.objects.get(owner=self.owner, nome='CustomPipe')
        self.assertTrue(pipeline_importado.stages.filter(nome='Etapa1').exists())
