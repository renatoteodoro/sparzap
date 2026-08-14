from unittest.mock import MagicMock, patch

from django.test import TestCase

from core.factories import make_ai_config

from . import services
from .crypto import decrypt_api_key, encrypt_api_key
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
        mock_anthropic_cls.assert_called_once_with(api_key=self.config.api_key, timeout=services.TIMEOUT_S)

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
            api_key=self.config.api_key, base_url=None, timeout=services.TIMEOUT_S,
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
            api_key=self.config.api_key, base_url=self.config.base_url, timeout=services.TIMEOUT_S,
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
