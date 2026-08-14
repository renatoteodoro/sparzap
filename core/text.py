"""
Normalização de texto para comparação de palavras-chave.

Compartilhado por `scripts` (condição de roteiro) e `triggers` (gatilho por
palavra-chave): os dois casam texto que o contato digitou no WhatsApp, e
precisam se comportar igual. Quem escreve no celular raramente acentua —
comparar "preço" com "preco" tem que dar casamento, senão a regra falha
justamente com a maioria das pessoas.
"""

import unicodedata


def normalizar(texto):
    """Minúsculas e sem acento: 'Qual o PREÇO?' -> 'qual o preco?'."""
    decomposto = unicodedata.normalize('NFKD', (texto or '').lower())
    return ''.join(c for c in decomposto if not unicodedata.combining(c))


def separar_termos(valor):
    """'pode, quero , sim' -> ['pode', 'quero', 'sim'], já normalizados."""
    # o .strip() tem que ser aplicado ao termo que vai ser comparado, nao só
    # no teste de "esta vazio": sem isso ' sem interesse' (com o espaco que
    # sobra depois da virgula) nunca casa com 'sem interesse'.
    return [normalizar(termo.strip()) for termo in (valor or '').split(',') if termo.strip()]


def contem_algum(texto, termos):
    """True se QUALQUER um dos termos aparecer no texto (comparação normalizada)."""
    normalizado = normalizar(texto)
    return any(termo in normalizado for termo in termos if termo)


def contem_todos(texto, termos):
    """True se TODOS os termos aparecerem no texto (comparação normalizada)."""
    normalizado = normalizar(texto)
    termos = [t for t in termos if t]
    return bool(termos) and all(termo in normalizado for termo in termos)
