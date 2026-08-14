import random
import re

VARIAVEIS_SUPORTADAS = ['nome', 'grupo', 'link', 'empresa']
VALOR_PADRAO = {
    'nome': '',
    'grupo': '',
    'link': '',
    'empresa': '',
}

_VAR_RE = re.compile(r'\{\{\s*(\w+)\s*\}\}')


def pick_variant(message):
    """Sorteia entre o conteudo principal e as variacoes (spintax) da mensagem."""
    opcoes = [message.conteudo] + [v.conteudo for v in message.variants.all()]
    opcoes = [o for o in opcoes if o]
    return random.choice(opcoes) if opcoes else message.conteudo


def render_message(message, contexto=None, usar_variante=True):
    """Renderiza {{variavel}} no texto de uma Message a partir do contexto informado."""
    contexto = {**VALOR_PADRAO, **(contexto or {})}
    texto = pick_variant(message) if usar_variante else message.conteudo

    def substituir(match):
        chave = match.group(1)
        return str(contexto.get(chave, match.group(0)))

    return _VAR_RE.sub(substituir, texto)


def unknown_variables(texto):
    """Retorna as variaveis {{x}} usadas no texto que nao sao suportadas — usado na validacao do form."""
    encontradas = set(_VAR_RE.findall(texto))
    return sorted(encontradas - set(VARIAVEIS_SUPORTADAS))
