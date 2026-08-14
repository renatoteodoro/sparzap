# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Sparzap: automação de vendas e divulgação no WhatsApp. Django 5.0 + Celery +
Evolution API. Interface e domínio em **português brasileiro**.

## Comandos

Ambiente Windows com venv em `.venv/`. Os comandos assumem `.venv\Scripts\`.

```bash
# Desenvolvimento
.venv\Scripts\python manage.py runserver
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py check

# Testes
.venv\Scripts\python manage.py test                                    # suíte completa (128 testes)
.venv\Scripts\python manage.py test antiblock                          # um app
.venv\Scripts\python manage.py test antiblock.tests.CanSendTests        # uma classe
.venv\Scripts\python manage.py test antiblock.tests.CanSendTests.test_bloqueia_fora_da_janela   # um teste

# Cobertura
.venv\Scripts\python -m coverage run --source=. --omit=".venv/*,*/migrations/*,manage.py,*/tests.py" manage.py test
.venv\Scripts\python -m coverage report

# Lint e formatação (flake8 precisa fechar com 0 issues)
.venv\Scripts\python -m flake8
.venv\Scripts\python -m black .
.venv\Scripts\python -m isort .

# Celery (só com broker real; em dev o padrão é eager)
.venv\Scripts\celery -A core worker -l info
.venv\Scripts\celery -A core beat -l info

# Evolution API local para testar QR Code de verdade
docker compose -f docker-compose.evolution-local.yml up -d
```

Config de lint em `setup.cfg` (flake8/isort) e `pyproject.toml` (black):
linha de 120, aspas simples preservadas, migrations excluídas.

## Arquitetura

13 apps Django por domínio. `core` acumula dois papéis — pacote do projeto
(settings/wsgi/celery) **e** app "de casa" (landing, dashboard, `BaseModel`,
alertas, factories) — por isso suas rotas ficam direto em `core/urls.py`,
sem namespace, enquanto as outras entram por `include()` com `app_name`.

Camadas dentro de cada app: `models.py` → `services.py` (regra de negócio) →
`views.py` / `tasks.py` (cascas finas que delegam ao service).

### O gargalo obrigatório (RNF-04)

**Nenhum código envia mensagem chamando `EvolutionClient` diretamente.**
Tudo passa por `antiblock.services.dispatch`, que é o único ponto que aplica
limite diário, janela de operação, contador de falhas e auto-pausa após 5
falhas consecutivas. Enviar por fora quebra a proteção anti-banimento
inteira — é bug, não atalho.

Cadeia de um disparo de campanha:

```
start_campaign → build_audience (CampaignContact)
              → dispatch_campaign (task) → send_campaign_contact por contato,
                com countdown cumulativo de antiblock.next_delay_seconds
              → process_campaign_contact → can_send → ScriptRun
              → scripts.execute_step → antiblock.dispatch → EvolutionClient
```

Cadeia de uma mensagem recebida:

```
POST /webhooks/evolution/<instancia>/?token=... → valida token, deduplica por
message_id, persiste WebhookEvent → process_webhook_event (task)
→ upsert do contato → log no CRM → retoma scripts aguardando resposta
→ marca resposta em campanhas → avalia gatilhos
```

### Aquecimento de número

O `WarmupPlan` funciona **alterando `Instance.limite_diario`** dia a dia, em
curva linear. Não existe checagem paralela em `campaigns` — o `can_send` já
barra pelo limite. Não introduza uma segunda.

## Armadilhas reais deste projeto

Todas já causaram bug aqui. Não são hipóteses.

### Modo eager do Celery (padrão em dev)

Com `CELERY_TASK_ALWAYS_EAGER=True`, `apply_async(countdown=X)` **executa na
hora, síncrono**. Uma task que se reagenda quando bloqueada recursa
infinitamente até `RecursionError`. Por isso
`campaigns.services.process_campaign_contact` tem um guard explícito
(`if settings.CELERY_TASK_ALWAYS_EAGER: return 'aguardando_condicao'`).
Replique-o em qualquer task que se reagende.

### Testes que dependem do relógio

`antiblock.can_send` bloqueia fora da janela de operação da instância
(default 08:00–21:00). Um teste que crie `Instance` com o default e envie
**passa de dia e falha de madrugada**. Quando o teste não for sobre a janela,
abra-a: `janela_inicio=time(0,0)`, `janela_fim=time(23,59)` — ou use
`core.factories.make_instance`, que já faz isso. Para simular bloqueio de
forma determinística, use `limite_diario=0`, nunca a janela.

### `EVOLUTION_WEBHOOK_BASE_URL` não pode ser `localhost`

Com a Evolution em container, `localhost` ali é o próprio container. Os
webhooks nunca chegam e o sintoma é indireto: status da instância preso em
"aguardando QR" mesmo com o celular conectado. Em Docker Desktop use
`http://host.docker.internal:8000` e adicione o host em `ALLOWED_HOSTS`.

### Payload da Evolution varia entre versões

A v2.3.7 devolve o QR já como data URI completa (`data:image/png;base64,...`);
versões anteriores devolviam só o payload. Normalize na entrada e cubra as
duas formas no teste. O campo do número conectado também muda de nome
(`wuid`/`jid`/`user`).

Além disso, `instances.services.provision_instance` **engole `EvolutionError`**:
a `Instance` é criada localmente mesmo se a criação na Evolution falhar,
deixando registros órfãos que só falham depois, ao conectar.

### Ação que muda estado é POST

Inclusive logout — o `LogoutView` do Django rejeita GET com 405. Use
`<form method="post">` com `{% csrf_token %}`, nunca `<a href>`.

### Storage de estáticos é condicional

`CompressedManifestStaticFilesStorage` exige `collectstatic` prévio, o que
quebra qualquer teste que renderize `{% static %}`. Por isso `core/settings.py`
escolhe o storage por `DEBUG`. Não torne incondicional.

## Convenções

- **Idioma**: domínio em português (campos, status, `verbose_name`, mensagens
  ao usuário, comentários); framework em inglês (nomes de classe,
  `get_queryset`, `form_valid`). Aspas simples em todo Python.
- **Models** herdam de `core.models.BaseModel`. Status como constante de
  classe + `_CHOICES`, nunca string solta. `Meta` com `verbose_name` PT e
  `ordering` explícito. `__str__` sempre.
- **Isolamento por usuário (RNF-02)**: todo queryset filtra por `owner`. Views
  CRUD usam o `OwnedQuerysetMixin` local do app; views de ação filtram
  explícito (`get_object_or_404(Model.objects.filter(owner=request.user), pk=pk)`).
- **Forms**: classes CSS vêm de `core.forms.apply_input_classes`, nunca
  Tailwind escrito no widget ou no template.
- **Templates** ficam em `templates/<app>/` na raiz, não em `<app>/templates/`.
  Cores sempre por token (`bg-surface`, `text-green`), nunca hexadecimal —
  os tokens trocam de valor entre os temas.
- **URLs**: segmentos em português, nomes de rota em inglês (`instances:connect`).
- **Tarefa periódica** se registra por migração de dados criando o
  `PeriodicTask` do django-celery-beat, com função reversa. Nunca editando o
  banco.
- **Logging**: um logger só (`sparzap`), mensagens em `chave=valor`, `%s` lazy.
- **Import tardio** dentro da função para quebrar ciclo entre apps, sempre com
  comentário. `except Exception` amplo só com `# noqa: BLE001` e justificativa.
- **Testes**: sempre com `EvolutionClient` mockado — nenhum teste chama a
  Evolution real. Use `core.factories` e `self.client.force_login(user)`.
  Todo bug corrigido ganha teste de regressão nomeado pelo comportamento
  correto, não pelo bug.

## Documentação

Ordem de precedência: **código > `docs/` > `PRD.md`**. Se um documento
divergir do código, atualize o documento.

- [`docs/README.md`](docs/README.md) — índice da documentação técnica
- [`docs/padroes-de-codigo.md`](docs/padroes-de-codigo.md) e
  [`docs/arquitetura.md`](docs/arquitetura.md) — leitura obrigatória antes de
  escrever código
- [`docs/evolution.md`](docs/evolution.md) — contrato da Evolution API
  (não está no context7; é fonte do próprio projeto)
- [`docs/tarefas-assincronas.md`](docs/tarefas-assincronas.md),
  [`docs/modelos.md`](docs/modelos.md), [`docs/rotas.md`](docs/rotas.md),
  [`docs/frontend.md`](docs/frontend.md), [`docs/testes.md`](docs/testes.md),
  [`docs/ambiente.md`](docs/ambiente.md)
- [`agents/README.md`](agents/README.md) — 4 agentes especializados na stack
- [`PRD.md`](PRD.md) — produto, RF/RNF e roadmap de sprints

## Estado

Sprints 0–19 concluídas: 13 apps, 128 testes passando, flake8 limpo,
integração validada contra Evolution API v2.3.7 real. O deploy em VPS está
escrito mas **não foi executado** contra servidor real (ver
[`docs/DEPLOY.md`](docs/DEPLOY.md)).

As fases F1–F6 do PRD (seção 14) dependem de decisões de negócio e
credenciais que ainda não existem — não implemente nada delas sem
solicitação explícita.
