# Agentes de IA — Time de Desenvolvimento

Agentes especializados na stack do **Sparzap** (Django 5.0 · DRF ·
Celery + Redis · PostgreSQL/SQLite · TailwindCSS via CDN · Evolution API).

Cada agente cobre um papel do time, com as convenções reais do projeto e as
ferramentas MCP certas para a sua função.

---

## Índice

| Agente | Arquivo | MCP | Papel |
|---|---|---|---|
| [Django Backend](#django-backend) | [django-backend.md](django-backend.md) | context7 | Models, services, views, forms, API REST |
| [Integrações & Automação](#integrações--automação) | [evolution-celery.md](evolution-celery.md) | context7 | Evolution API, webhooks, Celery, AntiBlock |
| [Django Frontend](#django-frontend) | [django-frontend.md](django-frontend.md) | context7 | Templates DTL, TailwindCSS, design system |
| [QA / Tester](#qa--tester) | [qa-tester.md](qa-tester.md) | Playwright | Testes de ponta a ponta no browser + suíte Django |

---

## Django Backend

**Arquivo:** [`django-backend.md`](django-backend.md)

Responsável pela camada de dados e de negócio dos 13 apps: models e
migrations, `services.py`, views (CBVs), forms e a API REST em DRF.
Garante o isolamento por `owner` exigido pelo RNF-02.

**Usa context7 MCP** para consultar documentação atualizada de Django 5,
DRF, drf-spectacular e python-decouple antes de implementar.

**Quando usar:**
- Criar ou alterar models e gerar migrations
- Escrever regra de negócio em `<app>/services.py`
- Criar CBVs, rotas e forms do painel
- Criar ou alterar serializers, viewsets e endpoints da API
- Ajustar `core/settings.py`, `admin.py`, permissões

---

## Integrações & Automação

**Arquivo:** [`evolution-celery.md`](evolution-celery.md)

Responsável por tudo que sai ou entra do WhatsApp e por tudo que roda fora
do ciclo request/response: o cliente HTTP da Evolution API, o recebimento e
processamento de webhooks, as tasks Celery e o controlador anti-banimento
(`antiblock`), incluindo limites diários, janela de operação e aquecimento
de número.

**Usa context7 MCP** para consultar documentação de Celery,
django-celery-beat, redis-py e requests.

**Quando usar:**
- Alterar `instances/evolution.py` ou adicionar um endpoint da Evolution
- Mexer no recebimento/processamento de webhooks (`webhooks/`)
- Criar, alterar ou agendar tasks Celery
- Mexer em `antiblock/` — ritmo, limites, janela, auto-pausa, aquecimento
- Diagnosticar mensagem não enviada, status de instância errado ou task travada

> Este é o agente mais sensível do projeto: o RNF-04 exige que **nenhum
> envio** vá direto à Evolution API fora de `antiblock.services.dispatch`.

---

## Django Frontend

**Arquivo:** [`django-frontend.md`](django-frontend.md)

Responsável pela interface: templates Django (DTL), componentes
TailwindCSS, design tokens, tema claro/escuro e o consumo do stream SSE de
progresso de campanha. Não há framework JS nem build step — tudo é
renderizado no servidor.

**Usa context7 MCP** para consultar documentação de TailwindCSS e Django
Template Language.

**Quando usar:**
- Criar ou alterar qualquer template em `templates/`
- Implementar componentes visuais (cards, badges, tabelas, modais, sidebar)
- Estilizar formulários (sempre via `core/forms.py`, nunca classe solta)
- Ajustar tokens em `static/css/tokens.css` ou o mapa Tailwind
- Garantir os dois temas, responsividade e contraste WCAG AA (RNF-09/RNF-10)

---

## QA / Tester

**Arquivo:** [`qa-tester.md`](qa-tester.md)

Valida o sistema de duas formas complementares: rodando a suíte Django
(128 testes) e navegando pela aplicação real no browser via **Playwright
MCP**, conferindo funcionalidade, design nos dois temas e ausência de
regressão. Gera relatório estruturado de bugs.

**Usa Playwright MCP** (`browser_navigate`, `browser_snapshot`,
`browser_click`, `browser_type`, `browser_take_screenshot`,
`browser_console_messages`).

**Quando usar:**
- Ao fim de qualquer feature, antes de considerá-la pronta
- Para validar os dois temas e a responsividade de uma tela nova
- Para testar fluxos completos (cadastro → instância → campanha → relatório)
- Para caçar regressão depois de refactor
- Para escrever o teste de regressão de um bug corrigido

---

## Como os agentes se complementam

```
Backend      →  models, services, views, forms, API
Integrações  →  Evolution API, webhooks, Celery, AntiBlock
Frontend     →  templates, componentes, tokens, temas
QA           →  valida no browser + suíte Django, reporta bugs
```

Backend e Frontend trabalham em paralelo. Integrações entra sempre que a
feature toca WhatsApp ou processamento assíncrono. QA fecha o ciclo: nada é
considerado pronto sem `manage.py test` verde, `flake8` com 0 issues e
validação no browser.

---

## Fontes de verdade

Todos os agentes seguem, nesta ordem:

1. **O código** — em conflito com qualquer documento, o código vence
2. [`docs/`](../docs/README.md) — referência técnica por tema
3. [`PRD.md`](../PRD.md) — produto, requisitos (RF/RNF) e roadmap de sprints

Leitura obrigatória antes de escrever código:
[`docs/padroes-de-codigo.md`](../docs/padroes-de-codigo.md) e
[`docs/arquitetura.md`](../docs/arquitetura.md).

Se um destes arquivos de agente divergir do código, **atualize o arquivo do
agente**.

---

## Estado do projeto

Sprints 0–19 concluídas: os 13 apps existem, 128 testes passam, a
integração com a Evolution API foi validada contra uma instância real
(v2.3.7). O deploy em VPS está escrito mas **não foi executado** contra um
servidor real (ver [`docs/DEPLOY.md`](../docs/DEPLOY.md)).

As fases F1–F6 do PRD (seção 14) dependem de decisões de negócio e
credenciais que ainda não existem — não implemente nada delas sem
solicitação explícita.

---

## Pré-requisitos de MCP

Estes agentes assumem dois MCP servers configurados:

| MCP | Usado por | Ferramentas principais |
|---|---|---|
| **context7** | Backend, Integrações, Frontend | `resolve-library-id`, `get-library-docs` |
| **Playwright** | QA | `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_take_screenshot` |

Sem eles os agentes ainda funcionam, mas perdem o principal: código baseado
em documentação atual e validação no browser real.
