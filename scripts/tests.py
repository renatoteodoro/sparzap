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
