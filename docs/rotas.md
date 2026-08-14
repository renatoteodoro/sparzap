# Rotas

Todas as rotas do painel exigem login. Os endereços são em português; os
nomes de rota (`{% url %}` / `reverse`) em inglês, no formato `app:nome`.

## Públicas

| URL | Nome | O que é |
|---|---|---|
| `/` | `landing` | Página pública |
| `/healthz/` | `healthz` | Healthcheck (banco, broker, Evolution) |
| `/admin/` | — | Django Admin |

## Contas — `/contas/` (`accounts:`)

| URL | Nome |
|---|---|
| `cadastro/` | `signup` |
| `entrar/` | `login` |
| `sair/` | `logout` — **só POST** |
| `senha/redefinir/` | `password_reset` |
| `senha/redefinir/enviado/` | `password_reset_done` |
| `senha/redefinir/<uidb64>/<token>/` | `password_reset_confirm` |
| `senha/redefinir/concluido/` | `password_reset_complete` |

## Painel

| URL | Nome |
|---|---|
| `/painel/` | `dashboard` |

## Instâncias — `/instancias/` (`instances:`)

| URL | Nome | Método |
|---|---|---|
| `` | `list` | GET |
| `nova/` | `create` | GET/POST |
| `<pk>/editar/` | `update` | GET/POST |
| `<pk>/remover/` | `delete` | GET/POST |
| `<pk>/conectar/` | `connect` | GET — busca o QR Code na Evolution |
| `<pk>/status/` | `refresh_status` | POST |
| `<pk>/teste/` | `test_message` | POST |
| `<pk>/desativar/` | `deactivate` | POST |

## Contatos — `/contatos/` (`contacts:`)

| URL | Nome |
|---|---|
| `` | `list` |
| `novo/` · `<pk>/editar/` · `<pk>/remover/` | `create` · `update` · `delete` |
| `importar/` | `import` (CSV) |
| `exportar/` | `export` (CSV) |
| `opt-out/` | `bulk_opt_out` |
| `deduplicar/` | `dedupe` |
| `grupos/` | `groups` |
| `grupos/sincronizar/<instance_pk>/` | `group_sync` |
| `grupos/<pk>/extrair/` | `group_extract` (participantes → contatos) |
| `grupos/<pk>/remover-admin/` | `group_demote` |
| `grupos/<pk>/enviar/` | `group_send` |

## Mensagens — `/mensagens/` (`library:`)

| URL | Nome |
|---|---|
| `` · `nova/` · `<pk>/editar/` · `<pk>/remover/` | `list` · `create` · `update` · `delete` |
| `<pk>/preview/` | `preview` — renderiza variáveis e sorteia variação |
| `pastas/nova/` · `pastas/<pk>/remover/` | `folder_create` · `folder_delete` |

## Scripts — `/scripts/` (`scripts:`)

| URL | Nome |
|---|---|
| `` · `novo/` · `<pk>/` · `<pk>/editar/` · `<pk>/remover/` | `list` · `create` · `detail` · `update` · `delete` |
| `<pk>/duplicar/` | `duplicate` |
| `<pk>/testar/` | `test_run` |
| `<script_pk>/passos/novo/` | `step_create` |
| `<script_pk>/passos/<pk>/remover/` | `step_delete` |

## Campanhas — `/campanhas/` (`campaigns:`)

| URL | Nome |
|---|---|
| `` · `nova/` · `<pk>/` | `list` · `create` · `detail` |
| `<pk>/iniciar/` · `<pk>/pausar/` · `<pk>/retomar/` · `<pk>/cancelar/` | `start` · `pause` · `resume` · `cancel` (POST) |
| `<pk>/relatorio/` | `report` (CSV) |
| `<pk>/eventos/` | `progress_stream` — SSE |

## Gatilhos — `/gatilhos/` (`triggers:`)

| URL | Nome |
|---|---|
| `` · `novo/` · `<pk>/editar/` · `<pk>/remover/` | `list` · `create` · `update` · `delete` |
| `testar/` | `test` |
| `logs/` | `logs` |
| `agendadas/` | `scheduled_list` |
| `agendadas/<pk>/cancelar/` · `agendadas/<pk>/reagendar/` | `scheduled_cancel` · `scheduled_reschedule` |
| `agendar/<contact_pk>/` | `scheduled_create` |

## CRM — `/crm/` (`crm:`)

| URL | Nome |
|---|---|
| `` | `kanban` |
| `leads/` | `list` |
| `leads/exportar/` | `export` |
| `leads/<pk>/` | `detail` |
| `leads/<pk>/mover/` | `move` (POST) |
| `leads/<pk>/anotar/` | `note_create` (POST) |

## Aquecimento — `/aquecimento/` (`antiblock:`)

| URL | Nome |
|---|---|
| `` | `warmup` |
| `<instance_pk>/iniciar/` | `warmup_start` |
| `planos/<pk>/pausar/` · `planos/<pk>/retomar/` | `warmup_pause` · `warmup_resume` |

## Relatórios — `/relatorios/` (`reports:`)

| URL | Nome |
|---|---|
| `` | `index` |
| `entregas/exportar/` | `delivery_export` |
| `backup/` · `backup/exportar/` · `backup/importar/` | `backup` · `backup_export` · `backup_import` |

## Webhooks — `/webhooks/` (`webhooks:`)

| URL | Nome | Observação |
|---|---|---|
| `evolution/<instance_name>/` | `evolution` | POST, `csrf_exempt`. Exige `?token=<EVOLUTION_WEBHOOK_SECRET>`, senão 403 |

## API REST — `/api/`

Ver [api.md](api.md). Endpoints: `token/`, `schema/`, `schema/docs/`,
`instances/`, `campaigns/`, `contacts/`, `leads/`, `messages/schedule/`.
