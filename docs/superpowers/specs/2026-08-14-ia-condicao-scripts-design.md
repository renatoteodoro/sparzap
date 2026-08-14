# IA multi-provedor no passo de condição dos scripts

Data: 2026-08-14

## Contexto

O motor de scripts (`scripts/services.py`) resolve o passo "Condição" hoje
comparando a resposta do contato contra uma lista de termos
(`condicao_contem`, casamento por substring via `core.text.contem_algum`).
Isso é frágil: qualquer resposta que contenha um termo negativo em qualquer
posição ("não sei, mas pode mandar") é classificada como negativa, mesmo
quando a intenção real é positiva.

O objetivo é permitir classificar a intenção da resposta via IA, mantendo o
comportamento atual como fallback quando a IA não estiver configurada ou
falhar.

## Objetivo

- Permitir configurar, por conta (owner), uma ou mais credenciais de IA
  (provedor + modelo + API key).
- Permitir que um passo de condição use essa IA para decidir se a resposta
  do contato "bate" com uma descrição em linguagem natural, em vez de (ou
  além de) palavras-chave.
- Se a IA não estiver ativada no passo, ou a chamada falhar por qualquer
  motivo, o passo continua funcionando exatamente como hoje
  (`condicao_contem`).

## Fora de escopo

- Qualquer outro tipo de passo (`mensagem`, `delay`, `aguardar_resposta`,
  `mudar_etapa`) — não muda.
- Um passo de "chatbot com IA" que gera respostas livres — não faz parte
  desta entrega (é o item RF-55/E3 do PRD, ainda não priorizado).
- Campanhas, gatilhos, CRM — não mudam.
- Rotação/fallback automático entre provedores diferentes — se a chamada
  falhar, cai direto para o matching por palavra-chave, não tenta outro
  provedor de IA.

## Modelo de dados

### App novo: `ai`

```python
class AIConfig(BaseModel):
    PROVIDER_ANTHROPIC = 'anthropic'
    PROVIDER_OPENAI = 'openai'
    PROVIDER_GEMINI = 'gemini'
    PROVIDER_OPENAI_COMPATIVEL = 'openai_compativel'
    PROVIDER_CHOICES = [
        (PROVIDER_ANTHROPIC, 'Claude (Anthropic)'),
        (PROVIDER_OPENAI, 'OpenAI'),
        (PROVIDER_GEMINI, 'Google Gemini'),
        (PROVIDER_OPENAI_COMPATIVEL, 'Compatível com OpenAI (URL própria)'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_configs')
    nome = models.CharField('nome', max_length=100)
    provider = models.CharField('provedor', max_length=20, choices=PROVIDER_CHOICES)
    modelo = models.CharField('modelo', max_length=100, help_text='Ex.: claude-opus-5, gpt-5, gemini-3-flash')
    api_key_cifrada = models.TextField('api key (cifrada)')
    base_url = models.CharField(
        'URL base', max_length=255, blank=True,
        help_text='Obrigatório só para "Compatível com OpenAI" (ex.: OpenCode Zen, OpenRouter).',
    )
    ativo = models.BooleanField('ativo', default=True)

    class Meta:
        verbose_name = 'configuração de IA'
        verbose_name_plural = 'configurações de IA'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.get_provider_display()})'

    @property
    def api_key(self):
        from .crypto import decrypt_api_key
        return decrypt_api_key(self.api_key_cifrada)

    @api_key.setter
    def api_key(self, valor):
        from .crypto import encrypt_api_key
        self.api_key_cifrada = encrypt_api_key(valor)
```

A API key nunca é exposta em texto puro fora do `services.py` que faz a
chamada. `api_key_cifrada` é o único campo persistido; `api_key` é uma
property de conveniência para o form.

### `scripts.ScriptStep` — 3 campos novos

```python
usar_ia = models.BooleanField('usar IA para avaliar a condição', default=False)
ia_config = models.ForeignKey(
    'ai.AIConfig', on_delete=models.SET_NULL, null=True, blank=True,
    related_name='+', verbose_name='configuração de IA',
)
condicao_ia_descricao = models.TextField(
    'descrição para a IA', blank=True,
    help_text='O que conta como "match" — ex.: "o contato demonstrou interesse em receber o link do grupo".',
)
```

`condicao_contem` e `proximo_passo` continuam existindo sem alteração de
significado — são o fallback.

## Segurança

- `ai/crypto.py`: `encrypt_api_key(raw: str) -> str` / `decrypt_api_key(enc: str) -> str`,
  usando `cryptography.fernet.Fernet`. A chave de cifragem vem de
  `settings.AI_FIELD_ENCRYPTION_KEY` (via `python-decouple`, nova entrada em
  `.env`/`.env.example`). Em dev, se a variável não existir, deriva uma
  chave determinística a partir de `SECRET_KEY` (com log de aviso) para não
  quebrar `runserver`/testes sem configuração extra — em produção a
  variável deve ser definida explicitamente (documentar em `docs/ambiente.md`).
- O formulário de `AIConfig` nunca pré-preenche o campo de API key na
  edição — mostra em branco com placeholder "deixe em branco para manter a
  atual"; só grava um novo valor cifrado se o campo vier preenchido no POST.
- Nenhum log imprime a API key ou o conteúdo de `api_key_cifrada`.
- Isolamento por dono: `AIConfig` segue o mesmo padrão RNF-02 já usado nos
  outros apps (`OwnedQuerysetMixin`, `ia_config` filtrado por
  `owner=request.user` no `ScriptStepForm`, igual ao campo `message` hoje).

## Camada de chamada (`ai/services.py`)

```python
def classificar(config, descricao, texto):
    """Retorna True/False se a IA respondeu com sucesso, ou None se falhou
    (rede, auth, resposta inesperada) — None sinaliza 'caia no fallback'."""
```

- Monta um prompt curto e fixo: instrução para responder só `SIM` ou `NAO`,
  seguida da descrição do passo (`condicao_ia_descricao`) e da resposta
  literal do contato (`texto`).
- Despacha por `config.provider`:
  - `anthropic` → SDK `anthropic`, `client.messages.create(model=config.modelo, ...)`.
  - `openai` → SDK `openai`, `OpenAI(api_key=...)`.
  - `openai_compativel` → mesmo SDK `openai`, com `base_url=config.base_url`.
  - `gemini` → SDK `google-genai`.
- Timeout curto (10s) em toda chamada.
- `try/except Exception` amplo ao redor de cada chamada (`# noqa: BLE001` —
  qualquer falha de IA não pode derrubar o motor de scripts nem o
  processamento do webhook); loga `ai_classificacao_erro provider=... erro=...`
  e retorna `None`.
- Parse da resposta: primeira palavra, normalizada via `core.text.normalizar`
  (reaproveita a função já usada por `scripts`/`triggers`). `'sim'` → `True`,
  `'nao'` → `False`, qualquer outra coisa → loga `ai_resposta_inesperada` e
  retorna `None`.

## Integração no motor de scripts

`scripts/services._resolve_condicao(script, step, texto)`:

```python
def _resolve_condicao(script, step, texto):
    if step is None or step.tipo != ScriptStep.TIPO_CONDICAO:
        return step

    if step.usar_ia and step.ia_config_id:
        from ai.services import classificar
        resultado = classificar(step.ia_config, step.condicao_ia_descricao, texto)
        if resultado is not None:
            return step.proximo_passo if (resultado and step.proximo_passo) else next_step(step)
        logger.warning('script_ia_fallback_keyword run step=%s', step.id)

    # comportamento atual, inalterado
    from core.text import contem_algum, separar_termos
    if contem_algum(texto, separar_termos(step.condicao_contem)) and step.proximo_passo:
        return step.proximo_passo
    return next_step(step)
```

Import tardio de `ai.services` dentro da função, com comentário — mesma
convenção já usada para `library`, `antiblock`, `crm` em `scripts/services.py`
(quebra de ciclo entre apps).

## Interface

- Novo item de navegação "IA" (`templates/base_app.html`), apontando para
  `ai:list`.
- `templates/ai/list.html`, `form.html`, `confirm_delete.html` — mesmo
  padrão visual dos outros CRUDs do projeto (cards + tokens de cor).
- `ScriptStepForm` (`scripts/forms.py`) ganha os 3 campos novos; filtra
  `ia_config` por `owner` igual ao campo `message`.
- `templates/scripts/detail.html` não precisa de lógica condicional nova —
  o form já itera todos os campos genericamente, então os campos de IA
  aparecem junto dos demais (o usuário só preenche se for usar).

## Testes

- `ai/tests.py`: um teste por provedor cobrindo sucesso, erro de
  rede/timeout, e resposta fora do padrão `SIM`/`NAO` — todos mockando o
  SDK/client na fronteira (nunca uma chamada HTTP real), seguindo o mesmo
  padrão do `EvolutionClient` mockado em `antiblock`/`instances`.
- `scripts/tests.py`: novo teste de regressão para `_resolve_condicao` com
  `usar_ia=True` e `ai.services.classificar` mockado — cobre os 3 casos:
  IA retorna `True` (pula pro passo), IA retorna `False` (segue fallthrough),
  IA retorna `None` (cai pro `condicao_contem`, comportamento idêntico ao
  atual).
- `ai/crypto.py`: teste round-trip (`encrypt_api_key` → `decrypt_api_key`)
  e teste garantindo que o valor cifrado não contém a chave em texto puro.

## Dependências novas

`requirements.txt`: `anthropic`, `openai`, `google-genai`, `cryptography`.

## Migração e compatibilidade

- Nova app `ai` adicionada a `INSTALLED_APPS`, com sua própria migração
  inicial.
- Migração em `scripts` adicionando os 3 campos novos ao `ScriptStep`
  (`usar_ia` com `default=False`, `ia_config` e `condicao_ia_descricao`
  opcionais) — não quebra nenhum script existente, já que o default é
  "IA desligada".
- Nenhuma mudança de comportamento para scripts que não ativarem `usar_ia`.
