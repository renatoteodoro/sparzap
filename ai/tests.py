from django.test import TestCase

from .crypto import decrypt_api_key, encrypt_api_key


class CryptoTests(TestCase):
    def test_cifra_e_decifra_a_mesma_chave(self):
        original = 'sk-ant-minha-chave-secreta-123'
        cifrado = encrypt_api_key(original)
        self.assertNotEqual(cifrado, original)
        self.assertNotIn(original, cifrado)
        self.assertEqual(decrypt_api_key(cifrado), original)
