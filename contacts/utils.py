"""Normalização de números de WhatsApp/telefone brasileiros para E.164."""

import re

_MOBILE_PREFIXES = set('6789')


def normalize_br_number(raw):
    """
    Normaliza um número brasileiro para E.164 (+55DDDNUMERO).

    Aceita JIDs do WhatsApp ("5511987654321@s.whatsapp.net"), números com
    máscara ("(11) 98765-4321"), com ou sem DDI, e o formato antigo de
    celular sem o 9º dígito (adiciona automaticamente quando aplicável).

    Retorna None se não for possível reconhecer um número BR válido.
    """
    if not raw:
        return None

    raw = raw.split('@')[0]
    digits = re.sub(r'\D', '', raw)
    if not digits:
        return None

    if digits.startswith('55') and len(digits) in (12, 13):
        digits = digits[2:]
    elif len(digits) in (10, 11):
        pass
    else:
        return None

    ddd = digits[:2]
    subscriber = digits[2:]

    if len(subscriber) == 8 and subscriber[0] in _MOBILE_PREFIXES:
        subscriber = '9' + subscriber

    if len(subscriber) not in (8, 9):
        return None

    return f'+55{ddd}{subscriber}'


def format_display(e164_number):
    """Formata +55DDDNUMERO para exibição: (DD) 9XXXX-XXXX."""
    if not e164_number or not e164_number.startswith('+55'):
        return e164_number
    ddd = e164_number[3:5]
    subscriber = e164_number[5:]
    if len(subscriber) == 9:
        return f'({ddd}) {subscriber[:5]}-{subscriber[5:]}'
    return f'({ddd}) {subscriber[:4]}-{subscriber[4:]}'
