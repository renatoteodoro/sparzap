from cryptography.fernet import Fernet
from django.conf import settings


def _fernet():
    return Fernet(settings.AI_FIELD_ENCRYPTION_KEY.encode())


def encrypt_api_key(raw):
    return _fernet().encrypt(raw.encode()).decode()


def decrypt_api_key(cifrado):
    return _fernet().decrypt(cifrado.encode()).decode()
