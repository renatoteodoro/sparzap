# Arquitetura

Django 5 monolítico, dividido em apps por domínio. Toda comunicação com o
WhatsApp passa pela Evolution API (nunca por browser/extensão).

```
Navegador ──HTTP──> Django (web)  ──HTTP──> Evolution API ──> WhatsApp
                       │  ▲                      │
                       │  └──── webhook ─────────┘
                       ▼
                  Celery (worker + beat) ──> Redis (broker)
                       │
                       ▼
                  PostgreSQL / SQLite
```

## Apps

| App | Responsabilidade | Rota base |
|---|---|---|
| `core` | Settings, Celery, landing, dashboard, healthcheck, `BaseModel`, alertas, factories de teste | `/`, `/painel/`, `/healthz/` |
| `accounts` | `User` customizado (login por e-mail), cadastro, reset de senha | `/contas/` |
| `instances` | Instâncias do WhatsApp, QR Code, status, cliente HTTP da Evolution | `/instancias/` |
| `webhooks` | Recebimento e processamento dos eventos da Evolution | `/webhooks/` |
| `contacts` | Contatos, etiquetas, listas, grupos, import/export CSV, auto-demote | `/contatos/` |
| `library` | Biblioteca de mensagens, variações (spintax), variáveis `{{nome}}` | `/mensagens/` |
| `scripts` | Sequências de passos (mensagem/delay/aguardar resposta/condição) e o motor que as executa | `/scripts/` |
| `campaigns` | Campanhas de disparo em massa, público, progresso em tempo real | `/campanhas/` |
| `antiblock` | Controle de ritmo, limites, janela de operação, aquecimento de número | `/aquecimento/` |
| `triggers` | Gatilhos por palavra-chave e mensagens agendadas (follow-up) | `/gatilhos/` |
| `crm` | Pipeline, etapas, leads, histórico de conversa | `/crm/` |
| `reports` | Relatórios de entrega e backup/restauração de configuração | `/relatorios/` |
| `api` | API REST (DRF) com autenticação por token | `/api/` |

`core` acumula dois papéis: é o pacote do projeto Django (settings, wsgi,
asgi, celery) **e** o app "de casa". Por isso as rotas dele são declaradas
direto em `core/urls.py`, sem namespace, e as demais entram por `include()`
com namespace próprio.

## Camadas dentro de um app

```
models.py      → estrutura de dados (herda de core.models.BaseModel)
services.py    → regra de negócio; é aqui que a lógica mora
tasks.py       → wrappers Celery que chamam services
views.py       → HTTP: valida form, chama service, devolve resposta
forms.py       → validação de entrada + classes CSS do design system
urls.py        → rotas do app, com app_name
admin.py       → registro no Django Admin
tests.py       → testes do app
```

Nem todo app tem todos os arquivos — `reports` usa `backup.py` no lugar de
`services.py`, `campaigns` tem um `sse.py` extra, `instances` tem
`evolution.py` (o cliente HTTP).

## Fluxos principais

### Disparo de campanha

1. `campaigns.services.start_campaign` materializa o público
   (`build_audience`) em `CampaignContact` e enfileira `dispatch_campaign`.
2. `dispatch_campaign` agenda um `send_campaign_contact` por contato, com
   `countdown` cumulativo calculado por `antiblock.next_delay_seconds` —
   é isso que dá o espaçamento aleatório entre envios.
3. `process_campaign_contact` consulta `antiblock.can_send`; se liberado,
   cria um `ScriptRun` e chama `scripts.services.execute_step`.
4. O passo de mensagem chama `antiblock.services.dispatch`, **a única porta
   de saída para a Evolution API**.

### Recebimento de mensagem

1. Evolution faz `POST /webhooks/evolution/<instancia>/?token=...`.
2. `webhooks.views.receive_webhook` valida o token, deduplica por
   `message_id`, persiste um `WebhookEvent` e enfileira `process_webhook_event`.
3. `webhooks.services.process_event` roteia pelo tipo do evento
   (`messages.upsert`, `messages.update`, `connection.update`,
   `contacts.upsert`).
4. Uma mensagem recebida faz, em cadeia: upsert do contato → log no CRM →
   retomada de scripts que aguardavam resposta → marcação de resposta em
   campanhas → avaliação de gatilhos.

## Decisões que valem conhecer

- **`antiblock.dispatch` é gargalo obrigatório.** Nenhum código fora dele
  deve chamar `EvolutionClient` para enviar mensagem. É o que garante
  limite diário, janela de operação e auto-pausa por falhas consecutivas.
- **Progresso de campanha usa SSE, não WebSocket.** `campaigns/sse.py`
  entrega um `StreamingHttpResponse` com `text/event-stream`, evitando
  trazer Django Channels/ASGI só para isso.
- **Alertas não usam o próprio WhatsApp.** Se a única instância for
  justamente a que quebrou, não haveria como avisar. `core/alerts.py`
  manda para o log estruturado e, opcionalmente, para `ALERT_WEBHOOK_URL`.
- **Retry automático só em `GET`.** `instances/evolution.py` configura
  retry para leitura; envio de mensagem nunca é retentado no cliente HTTP,
  para não arriscar disparo duplicado.
