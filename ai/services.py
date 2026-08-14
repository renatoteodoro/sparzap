import logging
import re

from core.text import normalizar

logger = logging.getLogger('sparzap')

TIMEOUT_S = 10

PROMPT_TEMPLATE = (
    'Responda apenas com a palavra SIM ou a palavra NAO (sem acento, sem pontuação, '
    'sem nenhuma explicação) — nada além disso.\n\n'
    'Critério do que conta como SIM: {descricao}\n\n'
    'A pessoa está respondendo pelo celular, então a resposta pode vir com hesitação, '
    'erros de digitação ou frases incompletas. Julgue pela intenção geral, não apenas '
    'pela primeira palavra: se em algum ponto da resposta a pessoa concorda, autoriza '
    'ou pede para prosseguir — mesmo começando com "não sei", "talvez" ou outra dúvida — '
    'isso conta como SIM. Só responda NAO se a pessoa recusar, pedir para não enviar/parar, '
    'ou a resposta não tiver nenhum sinal de concordância.\n\n'
    'Resposta do contato: "{texto}"'
)


def classificar(config, descricao, texto):
    """
    Pergunta pro provedor de IA configurado se `texto` bate com `descricao`.

    Retorna True/False se a IA respondeu com sucesso, ou None se a chamada
    falhou por qualquer motivo (rede, autenticação, resposta fora do
    padrão SIM/NAO) -- None sinaliza pro chamador usar o fallback de
    palavra-chave, nunca deixa a exceção propagar pro motor de scripts.
    """
    prompt = PROMPT_TEMPLATE.format(descricao=descricao, texto=texto)

    try:
        if config.provider == config.PROVIDER_ANTHROPIC:
            bruto = _chamar_anthropic(config, prompt)
        elif config.provider in (config.PROVIDER_OPENAI, config.PROVIDER_OPENAI_COMPATIVEL):
            bruto = _chamar_openai(config, prompt)
        elif config.provider == config.PROVIDER_GEMINI:
            bruto = _chamar_gemini(config, prompt)
        else:
            logger.warning('ai_classificacao_provider_desconhecido provider=%s', config.provider)
            return None
    except Exception:  # noqa: BLE001 -- falha de IA nunca pode travar o motor de scripts
        logger.exception('ai_classificacao_erro provider=%s config=%s', config.provider, config.id)
        return None

    return _parse_resposta(bruto)


def _chamar_anthropic(config, prompt):
    import anthropic

    client = anthropic.Anthropic(api_key=config.api_key, timeout=TIMEOUT_S, max_retries=0)
    resposta = client.messages.create(
        model=config.modelo,
        max_tokens=16,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return next((bloco.text for bloco in resposta.content if bloco.type == 'text'), '')


def _chamar_openai(config, prompt):
    import openai

    client = openai.OpenAI(
        api_key=config.api_key,
        base_url=config.base_url or None,
        timeout=TIMEOUT_S,
        max_retries=0,
    )
    resposta = client.chat.completions.create(
        model=config.modelo,
        max_completion_tokens=16,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return resposta.choices[0].message.content or ''


def _chamar_gemini(config, prompt):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.api_key, http_options=types.HttpOptions(timeout=TIMEOUT_S * 1000))
    resposta = client.models.generate_content(model=config.modelo, contents=prompt)
    return resposta.text or ''


def _parse_resposta(bruto):
    normalizado = normalizar(bruto).strip()
    primeiro_token = normalizado.split()[0] if normalizado.split() else ''
    primeiro_token = re.sub(r'[^a-z]', '', primeiro_token)
    if primeiro_token == 'sim':
        return True
    if primeiro_token == 'nao':
        return False
    logger.warning('ai_resposta_inesperada resposta=%r', bruto[:200])
    return None
