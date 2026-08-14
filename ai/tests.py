from django.test import TestCase

from core.factories import make_ai_config

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
