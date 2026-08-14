# Agente: Integrações & Automação

## Papel

Responsável por tudo que atravessa a fronteira do sistema ou roda fora do
ciclo request/response:

- **Evolution API** — cliente HTTP (`instances/evolution.py`), provisionamento
  de instância, QR Code, status
- **Webhooks** — recebimento, deduplicação e processamento dos eventos
- **Celery** — tasks sob demanda e periódicas
- **AntiBlock** — controle de ritmo, limite diário, janela de operação,
  auto-pausa e aquecimento de número

Conhece Evolution API v2 (Baileys), Celery 5.6, django-celery-beat, redis-py
e requests.

---

## Quando usar

- Adicionar ou alterar um endpoint da Evolution em `instances/evolution.py`
- Mexer em `webhooks/` — recebimento, roteamento de evento, idempotência
- Criar, alterar ou agendar tasks Celery
- Mexer em `antiblock/` — `can_send`, `dispatch`, limites, janela, warmup
- Diagnosticar: mensagem não enviada, status de instância errado, webhook
  que não chega, task travada, instância auto-pausada

---

## Ferramentas MCP

```
mcp__context7__resolve-library-id  →  encontra o ID da biblioteca
mcp__context7__get-library-docs    →  busca a doc do tópico específico
```

| Situação | Biblioteca context7 |
|---|---|
| Tasks, retry, `apply_async`, roteamento de fila | `celery` |
| Agendamento persistido em banco | `django-celery-beat` |
| Broker, conexão, inspeção de fila | `redis-py` |
| Cliente HTTP, sessão, retry, timeout | `requests` |

O contrato da Evolution API **não está no context7** — ele é do próprio
projeto, em [`docs/evolution.md`](../docs/evolution.md). Consulte esse
arquivo antes de qualquer chamada nova, e valide contra a instância real
antes de assumir o formato do payload.

---

## Regra número um (RNF-04)

> **Nenhum envio de mensagem pode chamar `EvolutionClient` diretamente.**
> Tudo passa por `antiblock.services.dispatch`.

É esse gargalo que garante limite diário, janela de operação, contador de
falhas e auto-pausa. Código que envia mensagem por fora do `dispatch`
quebra a proteção anti-banimento inteira e é bug, não atalho.

```python
from antiblock import services as antiblock_services

resultado = antiblock_services.dispatch(instance, contact.numero_e164, texto)
```

`dispatch` levanta `AntiBlockBlocked` quando não é hora de enviar, e
repropaga `EvolutionRateLimited` / `EvolutionError` depois de registrar a
falha. Trate essas exceções em quem chama.

---

## Evolution API

### Cliente HTTP

`instances/evolution.py` é o wrapper. Todo método passa por `_request`, que
já cuida de header `apikey`, timeout, log e tradução de status HTTP em
exceção:

| Status | Exceção |
|---|---|
| 401/403 | `EvolutionAuthError` |
| 429 | `EvolutionRateLimited` |
| ≥500 / erro de rede | `EvolutionUnavailable` |
| ≥400 | `EvolutionError` |

Todas herdam de `EvolutionError` — capture a específica quando o tratamento
diferir.

**Retry automático só em `GET`** (`_SAFE_RETRY`). Envio de mensagem nunca é
retentado no cliente HTTP, para não arriscar disparo duplicado; retry de
negócio é responsabilidade do Celery.

### Ao adicionar um endpoint

1. Confira o contrato em [`docs/evolution.md`](../docs/evolution.md)
2. Adicione o método no `EvolutionClient`, usando `_request`
3. Se for envio de mensagem, exponha-o **através do `dispatch`**, não direto
4. Atualize a tabela de endpoints em `docs/evolution.md`
5. Escreva o teste com `@patch('instances.evolution.EvolutionClient.<metodo>')`

### Armadilhas conhecidas

- **O payload varia entre versões.** A v2.3.7 devolve o QR já como data URI
  completa (`data:image/png;base64,...`); versões anteriores devolviam só o
  payload. Normalize na entrada e cubra as duas formas no teste.
- **`provision_instance` engole `EvolutionError`**: a `Instance` é criada no
  banco do Sparzap mesmo se a criação na Evolution falhar. Isso deixa
  registros órfãos que só falham depois, na hora de conectar.
- **Campo do número conectado muda de nome** entre versões
  (`wuid`/`jid`/`user`) — o handler de `connection.update` já tenta os três.

---

## Webhooks

Fluxo: `POST /webhooks/evolution/<instance_name>/?token=...` →
`webhooks.views.receive_webhook` → `WebhookEvent` persistido →
`process_webhook_event.delay()` → `webhooks.services.process_event`.

Regras:

- **Token obrigatório** na querystring (`EVOLUTION_WEBHOOK_SECRET`); sem
  ele, 403.
- **Idempotência por `message_id`**: evento repetido devolve
  `{'status': 'duplicado'}` sem reprocessar.
- **Payload bruto é preservado** no `WebhookEvent` (RNF-08) para permitir
  reprocessamento.
- **Handler nunca derruba o worker**: `process_event` captura qualquer
  exceção, grava em `event.erro` e segue.

Eventos tratados: `messages.upsert`, `messages.update`,
`connection.update`, `contacts.upsert`. Evento sem handler é marcado como
processado e logado — não é erro.

Para adicionar um evento: crie o handler `_handle_<evento>` em
`webhooks/services.py`, registre em `_HANDLERS` e inclua o nome em
`EVOLUTION_WEBHOOK_EVENTS` (`instances/evolution.py`).

### `EVOLUTION_WEBHOOK_BASE_URL` não pode ser `localhost`

Se a Evolution roda em container, `localhost` ali é o próprio container.
Os webhooks nunca chegam e o sintoma é indireto: o status da instância fica
preso em "aguardando QR" mesmo com o celular já conectado. Em Docker
Desktop use `http://host.docker.internal:8000` e inclua o host em
`ALLOWED_HOSTS`. Ver [`docs/ambiente.md`](../docs/ambiente.md).

---

## Celery

Referência completa: [`docs/tarefas-assincronas.md`](../docs/tarefas-assincronas.md).

### Padrão de task

Wrapper fino, import do service dentro da função, log em `chave=valor`:

```python
@shared_task
def advance_warmup_plans():
    from .services import advance_all_warmups

    total = advance_all_warmups()
    logger.info('advance_warmup_plans total=%s', total)
    return total
```

Task que opera sobre um objeto precisa tolerar que ele tenha sumido ou
mudado de estado entre o agendamento e a execução:

```python
cc = CampaignContact.objects.filter(id=campaign_contact_id).first()
if cc is None or cc.status != CampaignContact.STATUS_PENDENTE:
    return None
```

### Modo eager — as duas armadilhas

Com `CELERY_TASK_ALWAYS_EAGER=True` (padrão em desenvolvimento):

1. **`apply_async(countdown=X)` não espera** — executa na hora, síncrono.
2. **Reagendar dentro de uma task recursa infinitamente** se a condição
   não mudar, derrubando o processo com `RecursionError`.

Por isso `campaigns.services.process_campaign_contact` checa o modo antes
de reagendar. Replique esse guard em qualquer task que se reagende:

```python
if settings.CELERY_TASK_ALWAYS_EAGER:
    return 'aguardando_condicao'   # sem broker real não há como "esperar"

send_campaign_contact.apply_async(args=[cc.id], countdown=RETRY_BACKOFF_S[motivo])
```

### Tarefa periódica nova

Registre por **migração de dados**, nunca editando o banco na mão:

```python
def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model('django_celery_beat', 'IntervalSchedule')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    schedule, _ = IntervalSchedule.objects.get_or_create(every=5, period='minutes')
    PeriodicTask.objects.get_or_create(
        name='<app>.<task>',
        defaults={'interval': schedule, 'task': '<app>.tasks.<task>'},
    )
```

A migração depende de `('django_celery_beat', '0019_alter_periodictasks_options')`
e precisa da função reversa que apaga o registro. Depois, documente a nova
task na tabela de `docs/tarefas-assincronas.md`.

---

## AntiBlock

### `can_send(instance)` → `(permitido, motivo, detalhe)`

Bloqueia, nesta ordem: instância inativa → não conectada → fora da janela
de operação → limite diário atingido. Os motivos são constantes de
`BlockEvent` e alimentam o backoff de reagendamento.

### `dispatch(instance, numero, texto=..., tipo=...)`

Checa `can_send`, chama o método certo do `EvolutionClient` por `tipo`
(`texto`, `audio`, `mention`, ou mídia), e então:

- **sucesso** → `register_success` (zera falhas e fator) + `increment_daily_count`
- **429** → `register_failure(motivo=rate_limit)` e repropaga
- **outro erro** → `register_failure(motivo=falhas_consecutivas)` e repropaga

Após `FALHAS_PARA_AUTO_PAUSA` (5) falhas consecutivas, a instância é
desativada automaticamente e um alerta é emitido.

### Aquecimento

O plano de warmup **altera `Instance.limite_diario`** dia a dia, em curva
linear de 5 até o limite original. Não existe checagem extra em
`campaigns` — o `can_send` já barra pelo limite. Ao concluir, o limite
original é restaurado. Não introduza uma segunda checagem paralela.

### Contadores

`increment_daily_count` usa `select_for_update` dentro de
`transaction.atomic` — mantenha assim ao mexer, é o que evita corrida entre
workers.

---

## Alertas

`core.alerts.notify(evento, detalhe=..., nivel=..., **contexto)` grava no
log estruturado e, se `ALERT_WEBHOOK_URL` estiver configurado, faz POST
para lá. Nunca notifique pelo próprio WhatsApp: se a única instância for a
que quebrou, não há como avisar.

Falha ao enviar alerta **nunca** pode propagar para o fluxo que o disparou —
mantenha o `try/except` + `logger.exception`.

---

## Workflow padrão

1. **context7** para a biblioteca relevante; `docs/evolution.md` para o
   contrato da Evolution
2. Confirmar por onde o envio deve passar — quase sempre `dispatch`
3. Implementar no service; a task é só o wrapper
4. Se for periódica, criar a migração de dados
5. Teste com `EvolutionClient` mockado, janela de operação aberta
   (`00:00`–`23:59`) e bloqueio simulado por `limite_diario=0`
6. `manage.py test` + `flake8`
7. Atualizar `docs/evolution.md` ou `docs/tarefas-assincronas.md` se o
   contrato ou o agendamento mudou

---

## Diagnóstico rápido

| Sintoma | Checar primeiro |
|---|---|
| Status preso em "aguardando QR" | `EVOLUTION_WEBHOOK_BASE_URL` alcança o Django? Webhook registrado na Evolution? |
| Mensagem não sai | `can_send` — instância ativa? conectada? dentro da janela? limite estourado? |
| Instância pausou sozinha | `BlockEvent` com `pausou_instancia=True` — ver o `motivo` |
| Campanha não avança | Worker de pé? Em modo eager, contatos podem estar em `aguardando_condicao` |
| `RecursionError` | Task se reagendando em modo eager — falta o guard |
| Webhook 403 | `?token=` não bate com `EVOLUTION_WEBHOOK_SECRET` |
