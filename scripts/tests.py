from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from contacts.models import Contact
from instances.models import Instance

from . import services
from .models import Script, ScriptRun, ScriptStep


class ScriptEngineTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='dono@teste.com', password='x', nome='Dono')
        self.instance = Instance.objects.create(owner=self.owner, nome='I1', evolution_instance_name='i1')
        self.contact = Contact.objects.create(owner=self.owner, numero_e164='+5511987654321', nome='Fulano')
        self.script = Script.objects.create(owner=self.owner, nome='Funil 2 passos')

        self.step_wait = ScriptStep.objects.create(
            script=self.script, ordem=1, tipo=ScriptStep.TIPO_AGUARDAR_RESPOSTA, timeout_h=48
        )
        self.step_cond = ScriptStep.objects.create(
            script=self.script, ordem=2, tipo=ScriptStep.TIPO_CONDICAO, condicao_contem='quero'
        )
        self.step_fallback = ScriptStep.objects.create(
            script=self.script, ordem=3, tipo=ScriptStep.TIPO_DELAY, delay_s=0
        )
        self.step_match = ScriptStep.objects.create(script=self.script, ordem=4, tipo=ScriptStep.TIPO_DELAY, delay_s=0)
        self.step_cond.proximo_passo = self.step_match
        self.step_cond.save()

    def _start_run_aguardando(self):
        """Cria um run já parado no passo aguardar_resposta, sem deixar o check_timeout (eager) resolver sozinho."""
        with patch('scripts.tasks.check_timeout.apply_async'):
            run = services.start_run(self.script, self.contact, self.instance)
        run.refresh_from_db()
        return run

    def test_aguardar_resposta_pausa_o_run(self):
        run = self._start_run_aguardando()
        self.assertEqual(run.status, ScriptRun.STATUS_AGUARDANDO)
        self.assertEqual(run.passo_atual_id, self.step_wait.id)
        self.assertIsNotNone(run.aguardando_desde)

    def test_aguardar_resposta_nao_expira_sozinho_em_modo_eager(self):
        # Regressao: sem o guard de CELERY_TASK_ALWAYS_EAGER, o
        # apply_async(countdown=...) do check_timeout roda na hora (modo
        # eager real, sem mock), fazendo o run "pular" a espera e disparar o
        # passo seguinte no mesmo request -- as mensagens saiam todas juntas.
        run = services.start_run(self.script, self.contact, self.instance)
        run.refresh_from_db()
        self.assertEqual(run.status, ScriptRun.STATUS_AGUARDANDO)
        self.assertEqual(run.passo_atual_id, self.step_wait.id)

    def test_resposta_que_casa_condicao_vai_para_o_passo_match(self):
        run = self._start_run_aguardando()
        services.resume_waiting_steps(self.contact, 'eu quero sim')
        run.refresh_from_db()
        # step_match e' delay_s=0, sem proximo passo -> conclui o run
        self.assertEqual(run.status, ScriptRun.STATUS_CONCLUIDO)

    def test_resposta_que_nao_casa_vai_para_o_fallback(self):
        run = self._start_run_aguardando()
        services.resume_waiting_steps(self.contact, 'nao tenho interesse')
        run.refresh_from_db()
        self.assertEqual(run.status, ScriptRun.STATUS_CONCLUIDO)

    def test_diferencia_match_de_fallback_via_mock_de_advance(self):
        run = self._start_run_aguardando()
        with patch('scripts.services._advance'):
            services.resume_waiting_steps(self.contact, 'eu quero')
        run.refresh_from_db()
        # o run deve ter avancado para o passo de match (condicao resolvida),
        # mesmo sem _advance ter sido chamado (pois o passo resolvido nao e' None)
        self.assertEqual(run.passo_atual_id, self.step_match.id)

    def test_diferencia_fallback_sem_match(self):
        run = self._start_run_aguardando()
        with patch('scripts.services._advance'):
            services.resume_waiting_steps(self.contact, 'sem relacao nenhuma')
        run.refresh_from_db()
        self.assertEqual(run.passo_atual_id, self.step_fallback.id)

    def test_timeout_sem_resposta_segue_o_fallback(self):
        run = self._start_run_aguardando()
        with patch('scripts.services._advance'):
            services.handle_timeout(run.id, self.step_wait.id)
        run.refresh_from_db()
        self.assertEqual(run.passo_atual_id, self.step_fallback.id)

    def test_timeout_ignorado_se_run_ja_foi_retomado(self):
        run = self._start_run_aguardando()
        services.resume_waiting_steps(self.contact, 'eu quero')
        run.refresh_from_db()
        estado_apos_resposta = run.status
        # timeout tardio (job antigo) nao deve alterar nada, pois o run ja nao esta mais aguardando este passo
        services.handle_timeout(run.id, self.step_wait.id)
        run.refresh_from_db()
        self.assertEqual(run.status, estado_apos_resposta)


class CondicaoMultiTermoTests(TestCase):
    """
    `condicao_contem` aceita vários termos separados por vírgula e compara
    ignorando caixa e acento — quem responde pelo celular escreve "nao".
    """

    def setUp(self):
        from core.factories import make_script, make_user

        self.owner = make_user(email='cond@teste.com')
        self.script = make_script(owner=self.owner)
        self.condicao = ScriptStep.objects.create(
            script=self.script,
            ordem=1,
            tipo=ScriptStep.TIPO_CONDICAO,
            condicao_contem='nao, nao quero, sem interesse',
        )
        self.segue = ScriptStep.objects.create(script=self.script, ordem=2, tipo=ScriptStep.TIPO_MENSAGEM)
        self.desvio = ScriptStep.objects.create(script=self.script, ordem=3, tipo=ScriptStep.TIPO_MENSAGEM)
        self.condicao.proximo_passo = self.desvio
        self.condicao.save()

    def _resolve(self, texto):
        return services._resolve_condicao(self.script, self.condicao, texto)

    def test_casa_qualquer_um_dos_termos(self):
        for texto in ('nao quero', 'sem interesse agora', 'nao'):
            self.assertEqual(self._resolve(texto), self.desvio, texto)

    def test_ignora_acento_e_caixa(self):
        for texto in ('Não quero', 'NAO', 'NÃO QUERO', 'Sem Interesse'):
            self.assertEqual(self._resolve(texto), self.desvio, texto)

    def test_resposta_positiva_segue_o_fluxo_normal(self):
        for texto in ('pode sim!', 'quero sim', 'manda ai', 'que legal'):
            self.assertEqual(self._resolve(texto), self.segue, texto)

    def test_sem_resposta_segue_o_fluxo_normal(self):
        # timeout entrega texto vazio; nenhum termo casa
        self.assertEqual(self._resolve(''), self.segue)

    def test_condicao_vazia_nunca_desvia(self):
        self.condicao.condicao_contem = ''
        self.condicao.save()
        self.assertEqual(self._resolve('qualquer coisa'), self.segue)


class ExplicarErroTests(TestCase):
    """O teste de roteiro precisa dizer POR QUE falhou, não só 'status: Erro'."""

    def setUp(self):
        from core.factories import make_contact, make_instance, make_script, make_user

        self.owner = make_user(email='exp@teste.com')
        self.instance = make_instance(owner=self.owner, nome='Vendas')
        self.script = make_script(owner=self.owner)
        self.contact = make_contact(owner=self.owner)

    def _run(self, erro):
        return ScriptRun.objects.create(
            script=self.script,
            contact=self.contact,
            instance=self.instance,
            status=ScriptRun.STATUS_ERRO,
            erro=erro,
        )

    def test_fora_da_janela_explica_o_horario_e_o_que_fazer(self):
        import datetime

        self.instance.janela_inicio = datetime.time(8, 0)
        self.instance.janela_fim = datetime.time(21, 0)
        self.instance.save()

        texto = services.explicar_erro(self._run('fora_janela: janela 08:00:00–21:00:00'))
        self.assertIn('08:00', texto)
        self.assertIn('21:00', texto)
        self.assertIn('Vendas', texto)
        self.assertNotIn('fora_janela', texto)

    def test_limite_diario_explica(self):
        texto = services.explicar_erro(self._run('limite_diario: 30/30 hoje'))
        self.assertIn('limite diário', texto)
        self.assertIn('30/30', texto)

    def test_desconectado_manda_reconectar(self):
        texto = services.explicar_erro(self._run('desconectado: status atual: desconectado'))
        self.assertIn('QR', texto)

    def test_erro_desconhecido_e_repassado_cru(self):
        self.assertEqual(services.explicar_erro(self._run('algo inesperado')), 'algo inesperado')

    def test_sem_erro_registrado(self):
        self.assertIn('não registrado', services.explicar_erro(self._run('')))


class TesteDeRoteiroMostraErroTests(TestCase):
    def setUp(self):
        from core.factories import make_contact, make_instance, make_message, make_script, make_user

        self.owner = make_user(email='tr@teste.com')
        # instancia com a janela fechada: qualquer envio agora e' bloqueado
        import datetime

        self.instance = make_instance(
            owner=self.owner, janela_inicio=datetime.time(3, 0), janela_fim=datetime.time(3, 1)
        )
        self.contact = make_contact(owner=self.owner)
        self.script = make_script(owner=self.owner)
        ScriptStep.objects.create(
            script=self.script,
            ordem=1,
            tipo=ScriptStep.TIPO_MENSAGEM,
            message=make_message(owner=self.owner),
        )
        self.client.force_login(self.owner)

    @patch('django.utils.timezone.localtime')
    def test_falha_aparece_como_erro_e_nao_como_sucesso(self, mock_localtime):
        import datetime

        mock_localtime.return_value = datetime.datetime(2026, 1, 1, 10, 0)  # fora da janela 03:00-03:01

        r = self.client.post(
            f'/scripts/{self.script.pk}/testar/',
            {'contact': self.contact.pk, 'instance': self.instance.pk},
            follow=True,
        )
        avisos = [(m.level_tag, str(m)) for m in r.context['messages']]
        self.assertTrue(any(tag == 'error' for tag, _ in avisos), avisos)
        self.assertFalse(any(tag == 'success' for tag, _ in avisos), avisos)
        self.assertTrue(any('só envia entre' in txt for _, txt in avisos), avisos)
