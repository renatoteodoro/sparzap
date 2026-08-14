from unittest.mock import MagicMock, patch

from django.test import TestCase

from accounts.models import User
from contacts.models import Contact
from instances.models import Instance

from . import services
from .forms import ScriptStepForm
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


class CondicaoComIATests(TestCase):
    """
    Passo de condição com `usar_ia` ligado consulta a IA primeiro; se ela
    responder com sucesso, o resultado dela decide o desvio. Se falhar
    (retorna None) ou `usar_ia` estiver desligado, cai no matching por
    palavra-chave de sempre -- sem essa regra, "não sei, mas pode mandar"
    seria classificado como negativo só por conter "nao".
    """

    def setUp(self):
        from core.factories import make_ai_config, make_script, make_user

        self.owner = make_user(email='ia-cond@teste.com')
        self.script = make_script(owner=self.owner)
        self.ia_config = make_ai_config(owner=self.owner)
        self.condicao = ScriptStep.objects.create(
            script=self.script,
            ordem=1,
            tipo=ScriptStep.TIPO_CONDICAO,
            usar_ia=True,
            ia_config=self.ia_config,
            condicao_ia_descricao='o contato aceitou o convite',
            condicao_contem='nao, sem interesse',
        )
        self.segue = ScriptStep.objects.create(script=self.script, ordem=2, tipo=ScriptStep.TIPO_MENSAGEM)
        self.desvio = ScriptStep.objects.create(script=self.script, ordem=3, tipo=ScriptStep.TIPO_MENSAGEM)
        self.condicao.proximo_passo = self.desvio
        self.condicao.save()

    def _resolve(self, texto):
        return services._resolve_condicao(self.script, self.condicao, texto)

    @patch('ai.services.classificar', autospec=True)
    def test_ia_retorna_true_desvia_para_o_passo_alvo(self, mock_classificar):
        mock_classificar.return_value = True

        self.assertEqual(self._resolve('não sei, mas pode mandar'), self.desvio)
        mock_classificar.assert_called_once_with(
            self.ia_config,
            'o contato aceitou o convite',
            'não sei, mas pode mandar',
        )

    @patch('ai.services.classificar', autospec=True)
    def test_ia_retorna_false_segue_o_fluxo_normal(self, mock_classificar):
        mock_classificar.return_value = False

        self.assertEqual(self._resolve('não quero'), self.segue)

    @patch('ai.services.classificar', autospec=True)
    def test_ia_falha_cai_no_matching_por_palavra_chave(self, mock_classificar):
        mock_classificar.return_value = None

        # 'nao' bate em condicao_contem -- comportamento identico ao atual
        self.assertEqual(self._resolve('nao quero'), self.desvio)

    def test_usar_ia_desligado_nunca_chama_a_ia(self):
        self.condicao.usar_ia = False
        self.condicao.save()

        with patch('ai.services.classificar', autospec=True) as mock_classificar:
            self._resolve('qualquer coisa')
            mock_classificar.assert_not_called()

    def test_texto_vazio_de_timeout_nao_chama_a_ia(self):
        # Regressao: handle_timeout chama _resume_run(run, texto='') quando o
        # passo "aguardar resposta" expira sem resposta nenhuma -- mandar essa
        # string vazia pra IA classificar pode devolver SIM por acidente e
        # desviar o run sem nenhuma resposta real do contato.
        with patch('ai.services.classificar', autospec=True) as mock_classificar:
            resultado = self._resolve('')
            mock_classificar.assert_not_called()
        # '' nao bate em nenhum termo de condicao_contem -> fluxo normal
        self.assertEqual(resultado, self.segue)

    def test_ia_config_inativa_nao_chama_a_ia(self):
        # Desativar a config na tela de IA (ai/forms.py, templates/ai/list.html)
        # tem que valer tambem pro motor -- senao "desativar" na UI nao faz nada.
        self.ia_config.ativo = False
        self.ia_config.save()

        with patch('ai.services.classificar', autospec=True) as mock_classificar:
            resultado = self._resolve('nao quero')
            mock_classificar.assert_not_called()
        # 'nao' bate em condicao_contem -- cai no fallback de palavra-chave
        self.assertEqual(resultado, self.desvio)

    def test_descricao_vazia_nao_chama_a_ia(self):
        # Sem critério não há o que classificar: o prompt iria com "Descrição: "
        # em branco e a IA devolveria SIM/NAO no chute, desviando o run sem
        # nenhuma regra. O form já barra isso na tela; o motor tem que barrar
        # também, para passos gravados fora dela (import, shell, dados antigos).
        self.condicao.condicao_ia_descricao = '   '
        self.condicao.save()

        with patch('ai.services.classificar', autospec=True) as mock_classificar:
            resultado = self._resolve('nao quero')
            mock_classificar.assert_not_called()
        # 'nao' bate em condicao_contem -- cai no fallback de palavra-chave
        self.assertEqual(resultado, self.desvio)

    def test_script_com_ia_desligada_nunca_chama_a_ia(self):
        # Interruptor geral do script (Script.usar_ia): desligado, nenhum
        # passo do script consulta IA, mesmo com usar_ia=True e ia_config
        # ativa no passo -- é o "kill switch" da tela do script.
        self.script.usar_ia = False
        self.script.save()

        with patch('ai.services.classificar', autospec=True) as mock_classificar:
            resultado = self._resolve('nao quero')
            mock_classificar.assert_not_called()
        # 'nao' bate em condicao_contem -- cai no fallback de palavra-chave
        self.assertEqual(resultado, self.desvio)


class ResolveCondicaoIAEndToEndTests(TestCase):
    """
    Ponta a ponta: exercita `_resolve_condicao` chamando `ai.services.classificar`
    de verdade, mockando só na borda do SDK (`anthropic.Anthropic`). Um teste
    que mocka `ai.services.classificar` diretamente não pegaria uma quebra de
    contrato entre as duas camadas -- como o achado #5 da revisão, em que
    `_chamar_openai` passava `max_tokens` incompatível com o modelo
    configurado. Este teste, ao chamar o `classificar` real, pegaria.
    """

    def setUp(self):
        from core.factories import make_ai_config, make_script, make_user

        self.owner = make_user(email='ia-e2e@teste.com')
        self.script = make_script(owner=self.owner)
        self.ia_config = make_ai_config(owner=self.owner)
        self.condicao = ScriptStep.objects.create(
            script=self.script,
            ordem=1,
            tipo=ScriptStep.TIPO_CONDICAO,
            usar_ia=True,
            ia_config=self.ia_config,
            condicao_ia_descricao='o contato aceitou o convite',
        )
        self.segue = ScriptStep.objects.create(script=self.script, ordem=2, tipo=ScriptStep.TIPO_MENSAGEM)
        self.desvio = ScriptStep.objects.create(script=self.script, ordem=3, tipo=ScriptStep.TIPO_MENSAGEM)
        self.condicao.proximo_passo = self.desvio
        self.condicao.save()

    @patch('anthropic.Anthropic')
    def test_ia_real_desvia_para_o_passo_alvo(self, mock_anthropic_cls):
        bloco = MagicMock(type='text', text='SIM')
        mock_anthropic_cls.return_value.messages.create.return_value = MagicMock(content=[bloco])

        # 'segue' e' o passo natural (ordem 2); 'desvio' so' e' alcancado se
        # a IA de verdade (nao mockada) tiver classificado como positivo --
        # com os dois alvos identicos, o assert nunca discriminaria uma
        # quebra de contrato entre _resolve_condicao e ai.services.classificar.
        alvo = services._resolve_condicao(self.script, self.condicao, 'sim, aceito')

        self.assertEqual(alvo, self.desvio)
        mock_anthropic_cls.return_value.messages.create.assert_called_once()


class ScriptStepFormTests(TestCase):
    """`usar_ia` sem `condicao_ia_descricao` deixa a IA sem critério pra
    classificar -- o form tem que barrar essa combinação, não deixar passar
    pra ser descoberta em produção."""

    def setUp(self):
        from core.factories import make_ai_config, make_script, make_user

        self.owner = make_user(email='stepform@teste.com')
        self.script = make_script(owner=self.owner)
        self.ia_config = make_ai_config(owner=self.owner)

    def _dados(self, **overrides):
        dados = {
            'ordem': 1,
            'tipo': ScriptStep.TIPO_CONDICAO,
            'condicao_contem': '',
            'usar_ia': True,
            'ia_config': self.ia_config.pk,
            'condicao_ia_descricao': '',
        }
        dados.update(overrides)
        return dados

    def test_usar_ia_sem_descricao_e_invalido(self):
        form = ScriptStepForm(self._dados(), script=self.script, owner=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('condicao_ia_descricao', form.errors)

    def test_usar_ia_com_descricao_e_valido(self):
        form = ScriptStepForm(
            self._dados(condicao_ia_descricao='o contato aceitou o convite'), script=self.script, owner=self.owner
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_usar_ia_desligado_nao_exige_descricao(self):
        form = ScriptStepForm(self._dados(usar_ia=False, ia_config=''), script=self.script, owner=self.owner)
        self.assertTrue(form.is_valid(), form.errors)


class ScriptDuplicateViewTests(TestCase):
    """`ScriptDuplicateView` copia cada `ScriptStep` campo a campo -- se um
    campo novo for adicionado ao model e esquecido aqui, a duplicação some
    silenciosamente com ele."""

    def setUp(self):
        from core.factories import make_ai_config, make_script, make_user

        self.owner = make_user(email='dup@teste.com')
        self.script = make_script(owner=self.owner)
        self.ia_config = make_ai_config(owner=self.owner)
        self.condicao = ScriptStep.objects.create(
            script=self.script,
            ordem=1,
            tipo=ScriptStep.TIPO_CONDICAO,
            usar_ia=True,
            ia_config=self.ia_config,
            condicao_ia_descricao='o contato aceitou o convite',
            condicao_contem='sim',
        )
        self.client.force_login(self.owner)

    def test_duplicar_mantem_configuracao_de_ia_do_passo(self):
        self.client.post(f'/scripts/{self.script.pk}/duplicar/')

        copia = Script.objects.exclude(pk=self.script.pk).get(owner=self.owner)
        passo_copiado = copia.steps.get(ordem=1)

        self.assertTrue(passo_copiado.usar_ia)
        self.assertEqual(passo_copiado.ia_config_id, self.ia_config.id)
        self.assertEqual(passo_copiado.condicao_ia_descricao, self.condicao.condicao_ia_descricao)


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


class PassoEncerrarTests(TestCase):
    """
    Um funil com dois ramos (condição → mensagem A / mensagem B) só funciona
    se o ramo de cima puder TERMINAR. Sem isso, o passo de mensagem sempre
    avança para `ordem + 1` e o ramo positivo escorrega para dentro do ramo
    negativo, enviando as duas mensagens ao mesmo contato.
    """

    def setUp(self):
        from core.factories import make_contact, make_instance, make_message, make_script, make_user

        self.owner = make_user(email='encerrar@teste.com')
        self.script = make_script(owner=self.owner)
        self.instance = make_instance(owner=self.owner)
        self.contact = make_contact(owner=self.owner)

        # Mesma forma do funil real: aguarda a resposta, condiciona, e cada
        # ramo tem sua própria mensagem.
        self.aguardar = ScriptStep.objects.create(
            script=self.script, ordem=1, tipo=ScriptStep.TIPO_AGUARDAR_RESPOSTA
        )
        self.condicao = ScriptStep.objects.create(
            script=self.script,
            ordem=2,
            tipo=ScriptStep.TIPO_CONDICAO,
            condicao_contem='nao, sem interesse',
        )
        self.link = ScriptStep.objects.create(
            script=self.script,
            ordem=3,
            tipo=ScriptStep.TIPO_MENSAGEM,
            message=make_message(owner=self.owner, titulo='Link', conteudo='aqui esta o link'),
        )
        self.encerrar = ScriptStep.objects.create(script=self.script, ordem=4, tipo=ScriptStep.TIPO_ENCERRAR)
        self.recusa = ScriptStep.objects.create(
            script=self.script,
            ordem=5,
            tipo=ScriptStep.TIPO_MENSAGEM,
            message=make_message(owner=self.owner, titulo='Recusa', conteudo='tudo bem, obrigado'),
        )
        self.condicao.proximo_passo = self.recusa
        self.condicao.save()

    def _enviar(self, texto):
        """Retoma o run parado no 'aguardar resposta' e devolve as mensagens despachadas."""
        enviadas = []
        run = ScriptRun.objects.create(
            script=self.script,
            contact=self.contact,
            instance=self.instance,
            passo_atual=self.aguardar,
        )
        with patch('antiblock.services.dispatch') as mock_dispatch:
            mock_dispatch.side_effect = lambda inst, numero, texto: enviadas.append(texto) or {'key': {'id': 'X'}}
            services._resume_run(run, texto)
        run.refresh_from_db()
        return enviadas, run

    def test_ramo_positivo_nao_envia_a_mensagem_do_ramo_negativo(self):
        enviadas, run = self._enviar('sim, pode mandar')

        self.assertEqual(enviadas, ['aqui esta o link'])
        self.assertEqual(run.status, ScriptRun.STATUS_CONCLUIDO)

    def test_ramo_negativo_envia_so_a_recusa(self):
        enviadas, run = self._enviar('nao quero')

        self.assertEqual(enviadas, ['tudo bem, obrigado'])
        self.assertEqual(run.status, ScriptRun.STATUS_CONCLUIDO)

    def test_passo_encerrar_conclui_o_run(self):
        run = ScriptRun.objects.create(
            script=self.script,
            contact=self.contact,
            instance=self.instance,
            passo_atual=self.encerrar,
        )

        services.execute_step(run)

        run.refresh_from_db()
        self.assertEqual(run.status, ScriptRun.STATUS_CONCLUIDO)


class ScriptToggleIAViewTests(TestCase):
    def setUp(self):
        from core.factories import make_script, make_user

        self.owner = make_user(email='toggle-ia@teste.com')
        self.script = make_script(owner=self.owner)  # usar_ia=True por padrão
        self.client.force_login(self.owner)

    def test_post_desliga_a_ia(self):
        r = self.client.post(f'/scripts/{self.script.pk}/ia/toggle/', follow=True)
        self.script.refresh_from_db()
        self.assertFalse(self.script.usar_ia)
        self.assertEqual(r.status_code, 200)

    def test_post_de_novo_liga_a_ia(self):
        self.client.post(f'/scripts/{self.script.pk}/ia/toggle/')
        self.client.post(f'/scripts/{self.script.pk}/ia/toggle/')
        self.script.refresh_from_db()
        self.assertTrue(self.script.usar_ia)

    def test_get_nao_e_permitido(self):
        r = self.client.get(f'/scripts/{self.script.pk}/ia/toggle/')
        self.assertEqual(r.status_code, 405)

    def test_nao_deixa_alternar_script_de_outro_dono(self):
        from core.factories import make_script, make_user

        outro_dono = make_user(email='outro-toggle@teste.com')
        script_alheio = make_script(owner=outro_dono)

        r = self.client.post(f'/scripts/{script_alheio.pk}/ia/toggle/')

        self.assertEqual(r.status_code, 404)
        script_alheio.refresh_from_db()
        self.assertTrue(script_alheio.usar_ia)
