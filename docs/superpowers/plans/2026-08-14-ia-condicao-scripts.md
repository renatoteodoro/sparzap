# IA multi-provedor no passo de condição dos scripts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir configurar credenciais de IA (Claude, OpenAI, Gemini, ou
qualquer gateway compatível com a API da OpenAI) por conta, e usá-las no
passo "Condição" do motor de scripts para classificar a intenção da
resposta do contato — com fallback automático e transparente para o
matching por palavra-chave já existente quando a IA não estiver ativada
ou a chamada falhar.

**Architecture:** App Django novo `ai` com o modelo `AIConfig` (dono,
provedor, modelo, API key cifrada) e uma função `ai.services.classificar()`
que despacha para o SDK oficial de cada provedor, sempre retornando
`True`/`False`/`None` (`None` = falhou, use o fallback). `scripts.ScriptStep`
ganha 3 campos novos (`usar_ia`, `ia_config`, `condicao_ia_descricao`);
`scripts.services._resolve_condicao` tenta a IA primeiro quando ligada e
cai no `condicao_contem` de sempre se ela não responder.

**Tech Stack:** Django 5, SDKs oficiais `anthropic`, `openai` (cobre OpenAI
e qualquer gateway compatível, só trocando `base_url`), `google-genai`;
`cryptography` (Fernet) para cifrar a API key em repouso.

## Global Constraints

- Todo texto de domínio (labels, `verbose_name`, mensagens, help_text) em
  português; nomes de classe/método em inglês. Aspas simples em Python.
- Todo model novo herda de `core.models.BaseModel`.
- Isolamento por dono (RNF-02): toda queryset de `AIConfig` e `ia_config`
  filtra por `owner=request.user`, seguindo o `OwnedQuerysetMixin` local
  já usado em `library`/`scripts`.
- Forms usam `core.forms.apply_input_classes` — nunca Tailwind cru no
  widget.
- **Nenhum teste chama um provedor de IA real.** Todo teste que envolva
  `ai.services.classificar` mocka o SDK do provedor na fronteira (mesmo
  padrão do `EvolutionClient` mockado em `antiblock`/`instances`).
- Todo bug ou comportamento de fallback ganha teste de regressão nomeado
  pelo comportamento correto (`docs/testes.md`).
- Import tardio (dentro da função) para cruzar de `scripts` para `ai`,
  comentado com o motivo/sprint — mesma convenção já usada para
  `library`/`antiblock`/`crm` em `scripts/services.py`.
- Ao final de cada task: `.venv/Scripts/python -m flake8` com 0 issues.
  Ao final do plano inteiro: `.venv/Scripts/python -m black .` e
  `.venv/Scripts/python -m isort .`, e a suíte completa
  (`manage.py test`) verde.
- A API key nunca aparece em log, nunca é pré-preenchida de volta no
  formulário de edição, e nunca é serializada em texto puro em nenhuma
  resposta HTTP.

---

### Task 1: Esqueleto do app `ai`, settings, e cifragem da API key

**Files:**
- Modify: `requirements.txt`
- Create: `ai/__init__.py`
- Create: `ai/apps.py`
- Create: `ai/crypto.py`
- Create: `ai/tests.py`
- Modify: `core/settings.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `ai.crypto.encrypt_api_key(raw: str) -> str`,
  `ai.crypto.decrypt_api_key(cifrado: str) -> str`. Usadas pela Task 2
  (`AIConfig.api_key` property).
- Produces: `settings.AI_FIELD_ENCRYPTION_KEY` (str, chave Fernet válida —
  44 chars base64 urlsafe).

- [ ] **Step 1: Instalar e fixar a versão do `cryptography`**

```
.venv/Scripts/pip install cryptography
.venv/Scripts/pip show cryptography
```

Anote a versão exata mostrada em `Version:` (ex.: `44.0.0`) — vai ser
usada no próximo passo.

- [ ] **Step 2: Adicionar ao `requirements.txt`**

Abra `requirements.txt` e adicione uma linha no final (troque `X.Y.Z` pela
versão anotada no passo anterior):

```
cryptography==X.Y.Z
```

- [ ] **Step 3: Criar o esqueleto do app `ai`**

`ai/__init__.py` (vazio):

```python
```

`ai/apps.py`:

```python
from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai'
```

- [ ] **Step 4: Registrar o app em `INSTALLED_APPS`**

Em `core/settings.py`, modifique o bloco (linhas 32-56 hoje):

```python
INSTALLED_APPS = [
'django.contrib.admin',
'django.contrib.auth',
'django.contrib.contenttypes',
'django.contrib.sessions',
'django.contrib.messages',
'django.contrib.staticfiles',
'rest_framework',
'rest_framework.authtoken',
'drf_spectacular',
'django_celery_beat',
'core',
'accounts',
'instances',
'webhooks',
'contacts',
'library',
'scripts',
'campaigns',
'antiblock',
'triggers',
'crm',
'reports',
'api',
'ai',
]
```

(adicionada a linha `'ai',` no final, antes do `]`).

- [ ] **Step 5: Configurar `AI_FIELD_ENCRYPTION_KEY`**

Em `core/settings.py`, logo depois da linha `SECRET_KEY = config(...)`
(linha 11), adicione:

```python
# Cifra as API keys de IA em repouso (ai.crypto). Em produção, defina de
# verdade em .env — gere com:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Sem a variável (dev/teste), deriva uma chave determinística do SECRET_KEY
# para não exigir configuração extra — nunca use esse fallback em produção.
AI_FIELD_ENCRYPTION_KEY = config('AI_FIELD_ENCRYPTION_KEY', default='')
if not AI_FIELD_ENCRYPTION_KEY:
    import base64
    import hashlib

    AI_FIELD_ENCRYPTION_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()
```

- [ ] **Step 6: Documentar a variável em `.env.example`**

No final de `.env.example`, adicione:

```
# IA (Sprint 20) — configurações de IA por conta (ver app `ai`).
# Chave usada para cifrar as API keys dos provedores em repouso.
# Gere uma com: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Sem definir, dev/teste usam uma chave derivada do SECRET_KEY (não use isso em produção).
AI_FIELD_ENCRYPTION_KEY=
```

- [ ] **Step 7: Escrever o teste de cifragem (vai falhar — `ai/crypto.py` ainda não existe)**

`ai/tests.py`:

```python
from django.test import TestCase

from .crypto import decrypt_api_key, encrypt_api_key


class CryptoTests(TestCase):
    def test_cifra_e_decifra_a_mesma_chave(self):
        original = 'sk-ant-minha-chave-secreta-123'
        cifrado = encrypt_api_key(original)
        self.assertNotEqual(cifrado, original)
        self.assertNotIn(original, cifrado)
        self.assertEqual(decrypt_api_key(cifrado), original)
```

- [ ] **Step 8: Rodar o teste e confirmar que falha**

```
.venv/Scripts/python manage.py test ai
```

Esperado: `ModuleNotFoundError` ou `ImportError` mencionando `ai.crypto`
(o módulo ainda não existe).

- [ ] **Step 9: Implementar `ai/crypto.py`**

```python
from cryptography.fernet import Fernet
from django.conf import settings


def _fernet():
    return Fernet(settings.AI_FIELD_ENCRYPTION_KEY.encode())


def encrypt_api_key(raw):
    return _fernet().encrypt(raw.encode()).decode()


def decrypt_api_key(cifrado):
    return _fernet().decrypt(cifrado.encode()).decode()
```

- [ ] **Step 10: Rodar o teste de novo e confirmar que passa**

```
.venv/Scripts/python manage.py test ai
```

Esperado: `Ran 1 test ... OK`.

- [ ] **Step 11: Lint**

```
.venv/Scripts/python -m flake8 ai core
```

Esperado: sem saída (0 issues).

- [ ] **Step 12: Commit**

```bash
git add requirements.txt ai/__init__.py ai/apps.py ai/crypto.py ai/tests.py core/settings.py .env.example
git commit -m "Adiciona esqueleto do app ai com cifragem de API key (Fernet)"
```

---

### Task 2: Modelo `AIConfig`, migração e factory de teste

**Files:**
- Create: `ai/models.py`
- Create: `ai/migrations/__init__.py`
- Create: `ai/migrations/0001_initial.py` (gerado por `makemigrations`)
- Modify: `ai/tests.py`
- Modify: `core/factories.py`

**Interfaces:**
- Consumes: `ai.crypto.encrypt_api_key` / `decrypt_api_key` (Task 1).
- Produces: `ai.models.AIConfig` — campos `owner`, `nome`, `provider`
  (choices `AIConfig.PROVIDER_ANTHROPIC`/`PROVIDER_OPENAI`/
  `PROVIDER_GEMINI`/`PROVIDER_OPENAI_COMPATIVEL`), `modelo`, `base_url`,
  `ativo`; property `api_key` (get/set, cifra/decifra transparente).
  Usado pela Task 3 (`ai.services.classificar(config, ...)`) e pela
  Task 6 (`scripts.ScriptStep.ia_config`).
- Produces: `core.factories.make_ai_config(owner=None, nome=..., modelo=...,
  api_key=..., **kwargs) -> AIConfig`. Usado pelos testes das Tasks 3, 4 e 6.

- [ ] **Step 1: Escrever o modelo `AIConfig`**

`ai/models.py`:

```python
from django.conf import settings
from django.db import models

from core.models import BaseModel


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
    modelo = models.CharField(
        'modelo', max_length=100, help_text='Ex.: claude-opus-5, gpt-5, gemini-2.5-flash.'
    )
    api_key_cifrada = models.TextField('api key (cifrada)')
    base_url = models.CharField(
        'URL base',
        max_length=255,
        blank=True,
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

- [ ] **Step 2: Gerar a migração**

```
.venv/Scripts/python manage.py makemigrations ai
```

Esperado: cria `ai/migrations/0001_initial.py` (e `ai/migrations/__init__.py`
se ainda não existir) criando a tabela `ai_aiconfig`.

- [ ] **Step 3: Adicionar a factory `make_ai_config`**

No final de `core/factories.py`, adicione:

```python
def make_ai_config(owner=None, nome='Config IA Teste', modelo='claude-opus-5', api_key='chave-teste-123', **kwargs):
    from ai.models import AIConfig

    owner = owner or make_user()
    kwargs.setdefault('provider', AIConfig.PROVIDER_ANTHROPIC)
    return AIConfig.objects.create(owner=owner, nome=nome, modelo=modelo, api_key=api_key, **kwargs)
```

- [ ] **Step 4: Escrever teste do modelo (round-trip via a property, não só via `ai.crypto`)**

Adicione em `ai/tests.py`:

```python
from core.factories import make_ai_config

from .models import AIConfig


class AIConfigModelTests(TestCase):
    def test_api_key_e_persistida_cifrada_e_decifra_corretamente(self):
        config = make_ai_config(api_key='minha-chave-original')

        self.assertNotEqual(config.api_key_cifrada, 'minha-chave-original')

        do_banco = AIConfig.objects.get(pk=config.pk)
        self.assertEqual(do_banco.api_key, 'minha-chave-original')

    def test_str_mostra_nome_e_provedor(self):
        config = make_ai_config(nome='Minha Claude', provider=AIConfig.PROVIDER_ANTHROPIC)
        self.assertEqual(str(config), 'Minha Claude (Claude (Anthropic))')
```

- [ ] **Step 5: Rodar os testes e confirmar que passam**

```
.venv/Scripts/python manage.py test ai
```

Esperado: `Ran 3 tests ... OK`.

- [ ] **Step 6: Lint**

```
.venv/Scripts/python -m flake8 ai core
```

Esperado: sem saída.

- [ ] **Step 7: Commit**

```bash
git add ai/models.py ai/migrations ai/tests.py core/factories.py
git commit -m "Adiciona modelo AIConfig com API key cifrada e factory de teste"
```

---

### Task 3: Camada de chamada por provedor (`ai.services.classificar`)

**Files:**
- Modify: `requirements.txt`
- Create: `ai/services.py`
- Modify: `ai/tests.py`

**Interfaces:**
- Consumes: `AIConfig` (Task 2) — `config.provider`, `config.modelo`,
  `config.api_key`, `config.base_url`.
- Produces: `ai.services.classificar(config: AIConfig, descricao: str,
  texto: str) -> bool | None`. `True`/`False` = a IA respondeu com
  sucesso; `None` = falhou (rede, auth, resposta fora do padrão) — o
  chamador deve cair no fallback. Usado pela Task 6
  (`scripts.services._resolve_condicao`).
- Produces (constante usada nos testes): `ai.services.TIMEOUT_S = 10`.

- [ ] **Step 1: Instalar e fixar as versões dos 3 SDKs**

```
.venv/Scripts/pip install anthropic openai google-genai
.venv/Scripts/pip show anthropic
.venv/Scripts/pip show openai
.venv/Scripts/pip show google-genai
```

Anote as 3 versões exatas mostradas em `Version:`.

- [ ] **Step 2: Adicionar ao `requirements.txt`**

Adicione 3 linhas no final de `requirements.txt` (troque `X.Y.Z` pelas
versões anotadas):

```
anthropic==X.Y.Z
openai==X.Y.Z
google-genai==X.Y.Z
```

- [ ] **Step 3: Escrever os testes de `classificar` (vão falhar — `ai/services.py` ainda não existe)**

Acrescente em `ai/tests.py` (no topo do arquivo, ajuste o import
`from unittest.mock import MagicMock, patch`):

```python
from unittest.mock import MagicMock, patch

from . import services


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
```

- [ ] **Step 4: Rodar os testes e confirmar que falham**

```
.venv/Scripts/python manage.py test ai
```

Esperado: `ModuleNotFoundError`/`ImportError` mencionando `ai.services`.

- [ ] **Step 5: Implementar `ai/services.py`**

```python
import logging
import re

from core.text import normalizar

logger = logging.getLogger('sparzap')

TIMEOUT_S = 10

PROMPT_TEMPLATE = (
    'Responda apenas com a palavra SIM ou a palavra NAO (sem acento, sem pontuação, '
    'sem nenhuma explicação) — nada além disso.\n\n'
    'Critério do que conta como SIM: {descricao}\n\n'
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

    client = anthropic.Anthropic(api_key=config.api_key, timeout=TIMEOUT_S)
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
    )
    resposta = client.chat.completions.create(
        model=config.modelo,
        max_tokens=16,
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
```

- [ ] **Step 6: Rodar os testes de novo e confirmar que passam**

```
.venv/Scripts/python manage.py test ai
```

Esperado: `Ran 10 tests ... OK`.

- [ ] **Step 7: Lint**

```
.venv/Scripts/python -m flake8 ai
```

Esperado: sem saída.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt ai/services.py ai/tests.py
git commit -m "Adiciona ai.services.classificar com adaptador por provedor (Claude/OpenAI/Gemini/compatível)"
```

---

### Task 4: CRUD de `AIConfig` (form, views, urls, templates, navegação)

**Files:**
- Create: `ai/forms.py`
- Create: `ai/views.py`
- Create: `ai/urls.py`
- Create: `templates/ai/list.html`
- Create: `templates/ai/form.html`
- Create: `templates/ai/confirm_delete.html`
- Modify: `core/urls.py`
- Modify: `templates/components/sidebar.html`
- Modify: `ai/tests.py`

**Interfaces:**
- Consumes: `ai.models.AIConfig` (Task 2).
- Produces: rotas `ai:list`, `ai:create`, `ai:update`, `ai:delete` (URL
  base `/ia/`). Nenhuma outra task depende diretamente destas views.

- [ ] **Step 1: Criar o form `AIConfigForm`**

`ai/forms.py`:

```python
from django import forms

from core.forms import apply_input_classes

from .models import AIConfig

FIELD_ORDER = ['nome', 'provider', 'modelo', 'api_key', 'base_url', 'ativo']


class AIConfigForm(forms.ModelForm):
    api_key = forms.CharField(
        label='API key',
        required=False,
        widget=forms.PasswordInput(render_value=False),
    )

    class Meta:
        model = AIConfig
        fields = ['nome', 'provider', 'modelo', 'base_url', 'ativo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        self.order_fields(FIELD_ORDER)
        if self.instance.pk:
            self.fields['api_key'].help_text = 'Deixe em branco para manter a chave atual.'
        else:
            self.fields['api_key'].required = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        nova_chave = self.cleaned_data.get('api_key')
        if nova_chave:
            instance.api_key = nova_chave
        if commit:
            instance.save()
        return instance
```

- [ ] **Step 2: Criar as views**

`ai/views.py`:

```python
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import AIConfigForm
from .models import AIConfig


class OwnedQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class AIConfigListView(OwnedQuerysetMixin, ListView):
    model = AIConfig
    template_name = 'ai/list.html'
    context_object_name = 'configs'


class AIConfigCreateView(LoginRequiredMixin, CreateView):
    model = AIConfig
    form_class = AIConfigForm
    template_name = 'ai/form.html'
    success_url = reverse_lazy('ai:list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, 'Configuração de IA criada.')
        return super().form_valid(form)


class AIConfigUpdateView(OwnedQuerysetMixin, UpdateView):
    model = AIConfig
    form_class = AIConfigForm
    template_name = 'ai/form.html'
    success_url = reverse_lazy('ai:list')

    def form_valid(self, form):
        messages.success(self.request, 'Configuração de IA atualizada.')
        return super().form_valid(form)


class AIConfigDeleteView(OwnedQuerysetMixin, DeleteView):
    model = AIConfig
    template_name = 'ai/confirm_delete.html'
    success_url = reverse_lazy('ai:list')
```

- [ ] **Step 3: Criar as urls**

`ai/urls.py`:

```python
from django.urls import path

from . import views

app_name = 'ai'

urlpatterns = [
    path('', views.AIConfigListView.as_view(), name='list'),
    path('nova/', views.AIConfigCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.AIConfigUpdateView.as_view(), name='update'),
    path('<int:pk>/remover/', views.AIConfigDeleteView.as_view(), name='delete'),
]
```

- [ ] **Step 4: Registrar a rota em `core/urls.py`**

Em `core/urls.py`, adicione a linha `path('ia/', include('ai.urls')),`
logo antes de `path('api/', include('api.urls')),` (linha 31 hoje):

```python
    path('aquecimento/', include('antiblock.urls')),
    path('ia/', include('ai.urls')),
    path('api/', include('api.urls')),
```

- [ ] **Step 5: Criar os templates**

`templates/ai/list.html`:

```html
{% extends 'base_app.html' %}
{% block title %}IA — Sparzap{% endblock %}
{% block page_title %}IA{% endblock %}
{% block topbar_extra %}
<a href="{% url 'ai:create' %}" class="bg-dark-green text-white px-4 py-2 rounded-full text-sm font-semibold">+ Nova configuração</a>
{% endblock %}
{% block app_content %}
<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
  {% for config in configs %}
  <div class="bg-surface border border-silver rounded-card p-5">
    <div class="flex items-start justify-between mb-2">
      <h3 class="font-sans font-medium">{{ config.nome }}</h3>
      <span class="text-xs font-mono uppercase text-cool-gray">{{ config.get_provider_display }}</span>
    </div>
    <p class="text-sm text-cool-gray mb-1">Modelo: {{ config.modelo }}</p>
    <p class="text-sm mb-4">{% if config.ativo %}<span class="text-green">Ativa</span>{% else %}<span class="text-cool-gray">Inativa</span>{% endif %}</p>
    <div class="flex gap-2">
      <a href="{% url 'ai:update' config.pk %}" class="flex-1 text-center border border-silver rounded-link py-2 text-sm">Editar</a>
      <a href="{% url 'ai:delete' config.pk %}" class="text-danger text-sm px-3 py-2">Remover</a>
    </div>
  </div>
  {% empty %}
  <p class="text-sm text-cool-gray">Nenhuma configuração de IA cadastrada ainda.</p>
  {% endfor %}
</div>
{% endblock %}
```

`templates/ai/form.html`:

```html
{% extends 'base_app.html' %}
{% block title %}{% if object %}Editar{% else %}Nova{% endif %} configuração de IA — Sparzap{% endblock %}
{% block page_title %}{% if object %}Editar configuração de IA{% else %}Nova configuração de IA{% endif %}{% endblock %}
{% block app_content %}
<div class="max-w-lg bg-surface border border-silver rounded-card p-6">
  <form method="post" class="flex flex-col gap-4">
    {% csrf_token %}
    {% for field in form %}
      <div>
        <label class="block text-sm font-medium mb-1.5" for="{{ field.id_for_label }}">{{ field.label }}</label>
        {{ field }}
        {% if field.help_text %}<p class="text-xs text-cool-gray mt-1">{{ field.help_text }}</p>{% endif %}
        {% for erro in field.errors %}<p class="text-xs text-danger mt-1">{{ erro }}</p>{% endfor %}
      </div>
    {% endfor %}
    <div class="flex gap-2 mt-2">
      <button type="submit" class="bg-dark-green text-white rounded-full px-5 py-2.5 text-sm font-semibold">Salvar</button>
      <a href="{% url 'ai:list' %}" class="border border-silver rounded-link px-5 py-2.5 text-sm">Cancelar</a>
    </div>
  </form>
</div>
{% endblock %}
```

`templates/ai/confirm_delete.html`:

```html
{% extends 'base_app.html' %}
{% block title %}Remover configuração de IA — Sparzap{% endblock %}
{% block page_title %}Remover configuração de IA{% endblock %}
{% block app_content %}
<div class="max-w-md bg-surface border border-silver rounded-card p-6">
  <p class="text-sm mb-6">Remover a configuração <strong>{{ object.nome }}</strong>? Passos de script que usam essa configuração deixam de usar IA e caem no matching por palavra-chave.</p>
  <form method="post" class="flex gap-2">
    {% csrf_token %}
    <button type="submit" class="bg-danger text-white rounded-full px-5 py-2.5 text-sm font-semibold">Remover</button>
    <a href="{% url 'ai:list' %}" class="border border-silver rounded-link px-5 py-2.5 text-sm">Cancelar</a>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Adicionar o link "IA" na navegação**

Em `templates/components/sidebar.html`, modifique o bloco de `{% url %}`
(linhas 8-17 hoje) e o bloco de `{% sidebar_link %}` (linhas 19-28 hoje):

```html
    {% url 'dashboard' as url_dashboard %}
    {% url 'instances:list' as url_instances %}
    {% url 'contacts:list' as url_contacts %}
    {% url 'library:list' as url_library %}
    {% url 'scripts:list' as url_scripts %}
    {% url 'campaigns:list' as url_campaigns %}
    {% url 'triggers:list' as url_triggers %}
    {% url 'crm:kanban' as url_crm %}
    {% url 'antiblock:warmup' as url_warmup %}
    {% url 'ai:list' as url_ai %}
    {% url 'reports:index' as url_reports %}

    {% sidebar_link url_dashboard '📊' 'Dashboard' %}
    {% sidebar_link url_instances '📱' 'Instâncias' %}
    {% sidebar_link url_contacts '👥' 'Contatos' %}
    {% sidebar_link url_library '💬' 'Mensagens' %}
    {% sidebar_link url_scripts '🧩' 'Scripts' %}
    {% sidebar_link url_campaigns '🚀' 'Campanhas' %}
    {% sidebar_link url_triggers '⚡' 'Gatilhos' %}
    {% sidebar_link url_crm '📇' 'CRM' %}
    {% sidebar_link url_warmup '🔥' 'Aquecimento' %}
    {% sidebar_link url_ai '🤖' 'IA' %}
    {% sidebar_link url_reports '📈' 'Relatórios' %}
```

- [ ] **Step 7: Escrever os testes de view (porta de entrada real, `django.test.Client`)**

Acrescente em `ai/tests.py`:

```python
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
```

- [ ] **Step 8: Rodar os testes e confirmar que passam**

```
.venv/Scripts/python manage.py test ai
```

Esperado: `Ran 13 tests ... OK`.

- [ ] **Step 9: Testar manualmente na interface**

```
.venv/Scripts/python manage.py runserver
```

Acesse `http://127.0.0.1:8000/ia/`, crie uma configuração, edite sem
preencher a API key (confirme que ela não se perde) e remova. Confirme
que o link "IA" aparece na barra lateral.

- [ ] **Step 10: Lint**

```
.venv/Scripts/python -m flake8 ai templates
```

Esperado: sem saída.

- [ ] **Step 11: Commit**

```bash
git add ai/forms.py ai/views.py ai/urls.py templates/ai templates/components/sidebar.html core/urls.py ai/tests.py
git commit -m "Adiciona CRUD de AIConfig (form, views, urls, templates, navegação)"
```

---

### Task 5: Campos novos em `ScriptStep` e migração

**Files:**
- Modify: `scripts/models.py:70` (depois de `proximo_passo`, antes de `etapa_destino`)
- Create: `scripts/migrations/0008_...py` (nome exato gerado por `makemigrations`)

**Interfaces:**
- Consumes: `ai.models.AIConfig` (Task 2), via `'ai.AIConfig'` (referência
  de app por string, evita import direto entre apps).
- Produces: `ScriptStep.usar_ia` (bool), `ScriptStep.ia_config` (FK
  nullable), `ScriptStep.condicao_ia_descricao` (texto). Usados pela
  Task 6.

- [ ] **Step 1: Adicionar os 3 campos ao modelo**

Em `scripts/models.py`, logo depois do fechamento do campo `proximo_passo`
(depois da linha 70 — `)`, que fecha o `models.ForeignKey('self', ...)` —
e antes da linha `etapa_destino = models.CharField(...)`), adicione:

```python
    usar_ia = models.BooleanField(
        'usar IA para avaliar a condição',
        default=False,
        help_text='Só vale para o tipo "condição". Se a IA falhar, cai no matching por palavra-chave abaixo.',
    )
    ia_config = models.ForeignKey(
        'ai.AIConfig',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='configuração de IA',
    )
    condicao_ia_descricao = models.TextField(
        'descrição para a IA',
        blank=True,
        help_text=(
            'O que conta como positivo — ex.: "o contato demonstrou interesse '
            'em receber o link do grupo".'
        ),
    )
```

- [ ] **Step 2: Gerar a migração**

```
.venv/Scripts/python manage.py makemigrations scripts
```

Esperado: cria um novo arquivo em `scripts/migrations/` adicionando os 3
campos ao `ScriptStep` (não altera nenhum script existente — `usar_ia`
tem `default=False`, os outros dois são opcionais).

- [ ] **Step 3: Rodar a suíte de `scripts` pra confirmar que nada quebrou**

```
.venv/Scripts/python manage.py test scripts
```

Esperado: todos os testes existentes continuam passando (a suíte ainda
não usa os campos novos).

- [ ] **Step 4: Lint**

```
.venv/Scripts/python -m flake8 scripts
```

Esperado: sem saída.

- [ ] **Step 5: Commit**

```bash
git add scripts/models.py scripts/migrations
git commit -m "Adiciona campos usar_ia/ia_config/condicao_ia_descricao ao ScriptStep"
```

---

### Task 6: Integração no motor (`_resolve_condicao`) e no formulário do passo

**Files:**
- Modify: `scripts/services.py:151-169` (função `_resolve_condicao`)
- Modify: `scripts/forms.py` (`ScriptStepForm`)
- Modify: `scripts/tests.py`

**Interfaces:**
- Consumes: `ai.services.classificar` (Task 3), `ScriptStep.usar_ia` /
  `.ia_config` / `.condicao_ia_descricao` (Task 5).
- Produces: nenhuma interface nova — é o ponto de integração final.

- [ ] **Step 1: Escrever os testes de regressão (vão falhar — comportamento ainda não implementado)**

Acrescente em `scripts/tests.py`, depois da classe `CondicaoMultiTermoTests`:

```python
class CondicaoComIATests(TestCase):
    """
    Passo de condição com `usar_ia` ligado consulta a IA primeiro; se ela
    responder com sucesso, o resultado dela decide o desvio. Se falhar
    (retorna None) ou `usar_ia` estiver desligado, cai no matching por
    palavra-chave de sempre -- sem essa regra, "não sei, mas pode mandar"
    seria classificado como negativo só por conter "nao".
    """

    def setUp(self):
        from core.factories import make_ai_config, make_script, make_user

        self.owner = make_user(email='ia-cond@teste.com')
        self.script = make_script(owner=self.owner)
        self.ia_config = make_ai_config(owner=self.owner)
        self.condicao = ScriptStep.objects.create(
            script=self.script,
            ordem=1,
            tipo=ScriptStep.TIPO_CONDICAO,
            usar_ia=True,
            ia_config=self.ia_config,
            condicao_ia_descricao='o contato aceitou o convite',
            condicao_contem='nao, sem interesse',
        )
        self.segue = ScriptStep.objects.create(script=self.script, ordem=2, tipo=ScriptStep.TIPO_MENSAGEM)
        self.desvio = ScriptStep.objects.create(script=self.script, ordem=3, tipo=ScriptStep.TIPO_MENSAGEM)
        self.condicao.proximo_passo = self.desvio
        self.condicao.save()

    def _resolve(self, texto):
        return services._resolve_condicao(self.script, self.condicao, texto)

    @patch('ai.services.classificar')
    def test_ia_retorna_true_desvia_para_o_passo_alvo(self, mock_classificar):
        mock_classificar.return_value = True

        self.assertEqual(self._resolve('não sei, mas pode mandar'), self.desvio)
        mock_classificar.assert_called_once_with(
            self.ia_config, 'o contato aceitou o convite', 'não sei, mas pode mandar',
        )

    @patch('ai.services.classificar')
    def test_ia_retorna_false_segue_o_fluxo_normal(self, mock_classificar):
        mock_classificar.return_value = False

        self.assertEqual(self._resolve('não quero'), self.segue)

    @patch('ai.services.classificar')
    def test_ia_falha_cai_no_matching_por_palavra_chave(self, mock_classificar):
        mock_classificar.return_value = None

        # 'nao' bate em condicao_contem -- comportamento identico ao atual
        self.assertEqual(self._resolve('nao quero'), self.desvio)

    def test_usar_ia_desligado_nunca_chama_a_ia(self):
        self.condicao.usar_ia = False
        self.condicao.save()

        with patch('ai.services.classificar') as mock_classificar:
            self._resolve('qualquer coisa')
            mock_classificar.assert_not_called()
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```
.venv/Scripts/python manage.py test scripts.tests.CondicaoComIATests
```

Esperado: as 4 asserções falham (`_resolve_condicao` ainda ignora
`usar_ia`/`ia_config` — todos os casos caem no `condicao_contem`, então
`test_ia_retorna_false_segue_o_fluxo_normal` já passaria por acidente,
mas `test_ia_retorna_true_desvia_para_o_passo_alvo` falha, porque
"não sei, mas pode mandar" não bate em nenhum termo de
`condicao_contem` e hoje seguiria pro `self.segue`, não pro
`self.desvio`).

- [ ] **Step 3: Modificar `_resolve_condicao`**

Em `scripts/services.py`, substitua a função inteira (linhas 151-169
hoje):

```python
def _resolve_condicao(script, step, texto):
    """
    Se `step` for do tipo condição, resolve o alvo comparando `texto`; senão
    retorna o próprio `step`.

    Se o passo tiver `usar_ia` ligado e uma `ia_config` configurada, tenta
    classificar a resposta via IA primeiro. Se a IA responder com sucesso
    (True/False), o resultado dela decide o desvio. Se a IA falhar ou não
    estiver configurada, cai no matching por palavra-chave de sempre.

    `condicao_contem` aceita vários termos separados por vírgula e casa se
    QUALQUER um aparecer na resposta. A comparação ignora maiúsculas E
    acentos — quem responde pelo celular escreve "nao", "vc", "obrigado" sem
    acentuação, e uma condição que só reconhecesse "não" falharia com a
    maior parte das pessoas.
    """
    if step is None or step.tipo != ScriptStep.TIPO_CONDICAO:
        return step

    if step.usar_ia and step.ia_config_id:
        from ai.services import classificar  # Sprint 20: IA nos passos de condição

        resultado_ia = classificar(step.ia_config, step.condicao_ia_descricao, texto)
        if resultado_ia is not None:
            return step.proximo_passo if (resultado_ia and step.proximo_passo) else next_step(step)
        logger.warning('script_ia_fallback_keyword script=%s step=%s', script.id, step.id)

    from core.text import contem_algum, separar_termos

    if contem_algum(texto, separar_termos(step.condicao_contem)) and step.proximo_passo:
        return step.proximo_passo
    return next_step(step)
```

- [ ] **Step 4: Rodar os testes de novo e confirmar que passam**

```
.venv/Scripts/python manage.py test scripts.tests.CondicaoComIATests
```

Esperado: `Ran 4 tests ... OK`.

- [ ] **Step 5: Adicionar os campos ao `ScriptStepForm`**

Em `scripts/forms.py`, modifique a classe `ScriptStepForm` (linhas 18-40
hoje):

```python
class ScriptStepForm(forms.ModelForm):
    class Meta:
        model = ScriptStep
        fields = [
            'ordem',
            'tipo',
            'message',
            'delay_s',
            'timeout_h',
            'condicao_contem',
            'proximo_passo',
            'etapa_destino',
            'usar_ia',
            'ia_config',
            'condicao_ia_descricao',
        ]

    def __init__(self, *args, script=None, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        if script is not None:
            self.fields['proximo_passo'].queryset = script.steps.all()
        if owner is not None:
            from ai.models import AIConfig
            from library.models import Message

            self.fields['message'].queryset = Message.objects.filter(owner=owner)
            self.fields['ia_config'].queryset = AIConfig.objects.filter(owner=owner, ativo=True)
```

- [ ] **Step 6: Rodar a suíte completa de `scripts`**

```
.venv/Scripts/python manage.py test scripts
```

Esperado: todos os testes passam (os antigos + os 4 novos de
`CondicaoComIATests`).

- [ ] **Step 7: Testar manualmente na interface**

```
.venv/Scripts/python manage.py runserver
```

Crie uma `AIConfig` de teste (não precisa de chave real pra esse teste
visual — só confirmar o form), abra um script, adicione um passo tipo
"Condição" e confirme que os campos "usar IA para avaliar a condição",
"configuração de IA" e "descrição para a IA" aparecem no formulário de
adicionar passo, e que "configuração de IA" só lista configurações da
própria conta.

- [ ] **Step 8: Lint**

```
.venv/Scripts/python -m flake8 scripts
```

Esperado: sem saída.

- [ ] **Step 9: Commit**

```bash
git add scripts/services.py scripts/forms.py scripts/tests.py
git commit -m "Integra classificacao por IA no passo de condicao, com fallback pro matching por palavra-chave"
```

---

### Task 7: Documentação e verificação final

**Files:**
- Modify: `docs/modelos.md`
- Modify: `docs/arquitetura.md`

**Interfaces:**
- Nenhuma — task de polimento e verificação, sem código de produção novo.

- [ ] **Step 1: Documentar o app `ai` em `docs/arquitetura.md`**

Na tabela de apps (linhas 19-33 hoje), adicione uma linha antes de
`| \`api\` | ... |` (linha 33):

```
| `ai` | Configurações de IA por conta (provedor, modelo, API key) usadas pelo passo de condição dos scripts | `/ia/` |
```

- [ ] **Step 2: Documentar o modelo em `docs/modelos.md`**

Depois da seção `## scripts` (linhas 72-90 hoje), antes de `## campaigns`
(linha 92), adicione:

```markdown
## ai

**`AIConfig`** — credencial de IA configurada por conta (dono), usada
pelo passo "condição" dos scripts quando `usar_ia` está ligado.

| Campo | Observação |
|---|---|
| `provider` | `anthropic` · `openai` · `gemini` · `openai_compativel` (URL própria, ex.: OpenCode Zen) |
| `modelo` | String livre — ex. `claude-opus-5`, `gpt-5`, `gemini-2.5-flash` |
| `api_key_cifrada` | Nunca em texto puro; acesse via a property `api_key` (cifra/decifra com Fernet, `ai.crypto`) |
| `base_url` | Só usado quando `provider = openai_compativel` |

`ai.services.classificar(config, descricao, texto)` retorna `True`/`False`
se a IA respondeu com sucesso, ou `None` se falhou — `scripts.services.
_resolve_condicao` cai no `condicao_contem` de sempre quando recebe `None`.
```

E, na seção `## scripts` (linha 83), atualize a linha da tabela de
`condicao`:

```
| `condicao` | `condicao_contem`, `proximo_passo` (destino se a condição casar), `usar_ia`/`ia_config`/`condicao_ia_descricao` (classificação por IA, opcional — cai em `condicao_contem` se falhar) |
```

- [ ] **Step 3: Rodar a suíte completa do projeto**

```
.venv/Scripts/python manage.py test
```

Esperado: todos os testes passam (a suíte antiga + os novos de `ai` e
`scripts`).

- [ ] **Step 4: Rodar cobertura (opcional, mas recomendado)**

```
.venv/Scripts/python -m coverage run --source=. --omit=".venv/*,*/migrations/*,manage.py,*/tests.py" manage.py test
.venv/Scripts/python -m coverage report
```

- [ ] **Step 5: Lint completo**

```
.venv/Scripts/python -m flake8
```

Esperado: sem saída (0 issues).

- [ ] **Step 6: Formatação**

```
.venv/Scripts/python -m black .
.venv/Scripts/python -m isort .
```

Se algum arquivo for reformatado, revise o diff antes de seguir (não deve
mudar comportamento, só estilo).

- [ ] **Step 7: `manage.py check`**

```
.venv/Scripts/python manage.py check
```

Esperado: `System check identified no issues (0 silenced).`

- [ ] **Step 8: Commit**

```bash
git add docs/arquitetura.md docs/modelos.md
git commit -m "Documenta o app ai e os campos de IA do ScriptStep"
```
