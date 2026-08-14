from unittest.mock import MagicMock, patch

from django.test import TestCase

from core.factories import make_ai_config

from . import services
from .crypto import decrypt_api_key, encrypt_api_key
from .forms import AIConfigForm
from .models import AIConfig


class CryptoTests(TestCase):
    def test_cifra_e_decifra_a_mesma_chave(self):
        original = 'sk-ant-minha-chave-secreta-123'
        cifrado = encrypt_api_key(original)
        self.assertNotEqual(cifrado, original)
        self.assertNotIn(original, cifrado)
        self.assertEqual(decrypt_api_key(cifrado), original)


class AIConfigModelTests(TestCase):
    def test_api_key_e_persistida_cifrada_e_decifra_corretamente(self):
        config = make_ai_config(api_key='minha-chave-original')

        self.assertNotEqual(config.api_key_cifrada, 'minha-chave-original')

        do_banco = AIConfig.objects.get(pk=config.pk)
        self.assertEqual(do_banco.api_key, 'minha-chave-original')

    def test_str_mostra_nome_e_provedor(self):
        config = make_ai_config(nome='Minha Claude', provider=AIConfig.PROVIDER_ANTHROPIC)
        self.assertEqual(str(config), 'Minha Claude (Claude (Anthropic))')


class ClassificarAnthropicTests(TestCase):
    def setUp(self):
        self.config = make_ai_config(provider=AIConfig.PROVIDER_ANTHROPIC, modelo='claude-opus-5')

    @patch('anthropic.Anthropic')
    def test_ia_responde_sim_retorna_true(self, mock_anthropic_cls):
        bloco = MagicMock(type='text', text='SIM')
        mock_anthropic_cls.return_value.messages.create.return_value = MagicMock(content=[bloco])

        resultado = services.classificar(self.config, 'quer o link', 'sim quero')

        self.assertTrue(resultado)
        mock_anthropic_cls.assert_called_once_with(
            api_key=self.config.api_key, timeout=services.TIMEOUT_S, max_retries=0
        )

    @patch('anthropic.Anthropic')
    def test_ia_responde_nao_retorna_false(self, mock_anthropic_cls):
        bloco = MagicMock(type='text', text='NAO')
        mock_anthropic_cls.return_value.messages.create.return_value = MagicMock(content=[bloco])

        resultado = services.classificar(self.config, 'quer o link', 'nao quero')

        self.assertFalse(resultado)

    @patch('anthropic.Anthropic')
    def test_erro_de_rede_retorna_none_para_o_fallback(self, mock_anthropic_cls):
        mock_anthropic_cls.return_value.messages.create.side_effect = ConnectionError('timeout')

        resultado = services.classificar(self.config, 'quer o link', 'sim')

        self.assertIsNone(resultado)

    @patch('anthropic.Anthropic')
    def test_resposta_fora_do_padrao_retorna_none(self, mock_anthropic_cls):
        bloco = MagicMock(type='text', text='Talvez, não sei dizer ao certo.')
        mock_anthropic_cls.return_value.messages.create.return_value = MagicMock(content=[bloco])

        resultado = services.classificar(self.config, 'quer o link', 'talvez')

        self.assertIsNone(resultado)


class ClassificarOpenAITests(TestCase):
    def setUp(self):
        self.config = make_ai_config(provider=AIConfig.PROVIDER_OPENAI, modelo='gpt-5')

    @patch('openai.OpenAI')
    def test_ia_responde_sim_retorna_true(self, mock_openai_cls):
        escolha = MagicMock(message=MagicMock(content='SIM'))
        mock_openai_cls.return_value.chat.completions.create.return_value = MagicMock(choices=[escolha])

        resultado = services.classificar(self.config, 'quer o link', 'com certeza')

        self.assertTrue(resultado)
        mock_openai_cls.assert_called_once_with(
            api_key=self.config.api_key,
            base_url=None,
            timeout=services.TIMEOUT_S,
            max_retries=0,
        )


class ClassificarOpenAICompativelTests(TestCase):
    def setUp(self):
        self.config = make_ai_config(
            provider=AIConfig.PROVIDER_OPENAI_COMPATIVEL,
            modelo='algum-modelo',
            base_url='https://opencode-zen.exemplo/v1',
        )

    @patch('openai.OpenAI')
    def test_usa_a_base_url_configurada(self, mock_openai_cls):
        escolha = MagicMock(message=MagicMock(content='SIM'))
        mock_openai_cls.return_value.chat.completions.create.return_value = MagicMock(choices=[escolha])

        services.classificar(self.config, 'quer o link', 'sim')

        mock_openai_cls.assert_called_once_with(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=services.TIMEOUT_S,
            max_retries=0,
        )


class ClassificarGeminiTests(TestCase):
    def setUp(self):
        self.config = make_ai_config(provider=AIConfig.PROVIDER_GEMINI, modelo='gemini-2.5-flash')

    @patch('google.genai.Client')
    def test_ia_responde_sim_retorna_true(self, mock_client_cls):
        mock_client_cls.return_value.models.generate_content.return_value = MagicMock(text='SIM')

        resultado = services.classificar(self.config, 'quer o link', 'sim')

        self.assertTrue(resultado)
        mock_client_cls.assert_called_once()


class PromptTemplateTests(TestCase):
    """
    O template tem que ser NEUTRO: quem define o que conta como SIM é a
    `condicao_ia_descricao` do passo, nunca o template.

    Regressão: o template já teve um parágrafo fixo mandando responder SIM
    quando o contato "concorda, autoriza ou pede para prosseguir". Isso
    contradizia qualquer descrição de direção oposta ("o contato recusou o
    convite") e a IA — obedecendo à instrução mais específica, a fixa —
    invertia TODA classificação, mandando a mensagem de recusa pra quem
    tinha aceitado.
    """

    DIRECIONAIS = ('concorda', 'autoriza', 'prosseguir', 'recus', 'aceit', 'interesse', 'positiv', 'negativ')

    def test_template_nao_embute_direcao_semantica(self):
        prompt = services.PROMPT_TEMPLATE.format(descricao='DESCRICAO_DO_PASSO', texto='TEXTO_DO_CONTATO')
        esqueleto = prompt.replace('DESCRICAO_DO_PASSO', '').replace('TEXTO_DO_CONTATO', '').lower()

        for termo in self.DIRECIONAIS:
            self.assertNotIn(
                termo,
                esqueleto,
                f'"{termo}" no template presume a direção do critério e inverte descrições opostas',
            )

    def test_prompt_carrega_descricao_e_texto_do_passo(self):
        prompt = services.PROMPT_TEMPLATE.format(
            descricao='o contato recusou o convite',
            texto='sim, pode mandar',
        )

        self.assertIn('o contato recusou o convite', prompt)
        self.assertIn('sim, pode mandar', prompt)


class AIConfigFormTests(TestCase):
    """`base_url` é obrigatório para "Compatível com OpenAI" -- o próprio
    help_text do campo já diz isso; o form precisa aplicar, não só avisar."""

    def _dados(self, **overrides):
        dados = {
            'nome': 'Minha Config',
            'provider': AIConfig.PROVIDER_OPENAI_COMPATIVEL,
            'modelo': 'algum-modelo',
            'api_key': 'sk-teste',
            'base_url': '',
            'ativo': 'on',
        }
        dados.update(overrides)
        return dados

    def test_openai_compativel_sem_base_url_e_invalido(self):
        form = AIConfigForm(self._dados())
        self.assertFalse(form.is_valid())
        self.assertIn('base_url', form.errors)

    def test_openai_compativel_com_base_url_e_valido(self):
        form = AIConfigForm(self._dados(base_url='https://opencode-zen.exemplo/v1'))
        self.assertTrue(form.is_valid(), form.errors)

    def test_outro_provider_sem_base_url_e_valido(self):
        form = AIConfigForm(self._dados(provider=AIConfig.PROVIDER_ANTHROPIC, modelo='claude-opus-5'))
        self.assertTrue(form.is_valid(), form.errors)


class AIConfigViewsTests(TestCase):
    def setUp(self):
        from core.factories import make_user

        self.owner = make_user(email='view@teste.com')
        self.client.force_login(self.owner)

    def test_criar_configuracao_cifra_a_api_key(self):
        r = self.client.post(
            '/ia/nova/',
            {
                'nome': 'Minha Claude',
                'provider': AIConfig.PROVIDER_ANTHROPIC,
                'modelo': 'claude-opus-5',
                'api_key': 'sk-ant-secreta',
                'base_url': '',
                'ativo': 'on',
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        config = AIConfig.objects.get(owner=self.owner)
        self.assertEqual(config.api_key, 'sk-ant-secreta')
        self.assertNotIn(b'sk-ant-secreta', r.content)

    def test_editar_sem_preencher_api_key_mantem_a_atual(self):
        config = make_ai_config(owner=self.owner, nome='Original', api_key='chave-original')

        r = self.client.post(
            f'/ia/{config.pk}/editar/',
            {
                'nome': 'Renomeada',
                'provider': config.provider,
                'modelo': config.modelo,
                'api_key': '',
                'base_url': '',
                'ativo': 'on',
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        config.refresh_from_db()
        self.assertEqual(config.nome, 'Renomeada')
        self.assertEqual(config.api_key, 'chave-original')

    def test_lista_so_mostra_configuracoes_do_dono_logado(self):
        from core.factories import make_user

        outro_dono = make_user(email='outro@teste.com')
        make_ai_config(owner=outro_dono, nome='Não é minha')
        make_ai_config(owner=self.owner, nome='É minha')

        r = self.client.get('/ia/')

        self.assertContains(r, 'É minha')
        self.assertNotContains(r, 'Não é minha')
