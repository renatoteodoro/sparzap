# Tarefas assíncronas (Celery)

App Celery em `core/celery.py`, broker Redis, agendador
`django_celery_beat.schedulers:DatabaseScheduler` (as tarefas periódicas
ficam no banco, não em `CELERY_BEAT_SCHEDULE`).

```bash
.venv\Scripts\celery -A core worker -l info
.venv\Scripts\celery -A core beat -l info
```

## Modo eager (padrão em desenvolvimento)

Com `CELERY_TASK_ALWAYS_EAGER=True` as tasks executam **na hora e de forma
síncrona**, no mesmo processo — o projeto sobe sem Redis. Duas consequências
que já causaram problema real:

1. **`apply_async(countdown=X)` não espera.** Executa imediatamente. Todo
   agendamento com atraso vira execução direta.
2. **Reagendar dentro de uma task recursa.** Se a condição que motivou o
   reagendamento não mudar (ex.: fora da janela de operação), a recursão é
   infinita e derruba o processo com `RecursionError`.

Por isso `campaigns.services.process_campaign_contact` tem um guard
explícito: em modo eager, quando o AntiBlock bloqueia por um motivo
retentável, o contato fica pendente (`aguardando_condicao`) em vez de
reagendar. O próximo `dispatch_campaign` tenta de novo.

Ao escrever uma task que reagenda a si mesma, verifique
`settings.CELERY_TASK_ALWAYS_EAGER` antes.

## Tarefas periódicas

Registradas por **migração de dados** (`RunPython`) que cria o
`PeriodicTask` no `django_celery_beat`, com a função reversa apagando o
registro:

```python
def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model('django_celery_beat', 'IntervalSchedule')
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    schedule, _ = IntervalSchedule.objects.get_or_create(every=5, period='minutes')
    PeriodicTask.objects.get_or_create(
        name='instances.refresh_all_instances_status',
        defaults={'interval': schedule, 'task': 'instances.tasks.refresh_all_instances_status'},
    )
```

A migração precisa depender de `('django_celery_beat', '0019_alter_periodictasks_options')`.
Siga esse padrão ao adicionar uma nova — nada de editar o banco na mão.

### O que já está agendado

| Task | Frequência | O que faz |
|---|---|---|
| `instances.tasks.refresh_all_instances_status` | 5 min | Consulta `connectionState` de cada instância ativa na Evolution |
| `triggers.tasks.dispatch_due_scheduled_messages` | 5 min | Envia os follow-ups vencidos |
| `core.tasks.check_queue_size` | 5 min | Alerta se a fila passar de 500 tarefas (ignorado em modo eager) |
| `campaigns.tasks.check_failure_rates` | 15 min | Alerta campanhas em andamento com ≥30% de falha (mínimo 10 processados) |
| `webhooks.tasks.reconcile_missed_webhooks` | 15 min | Reprocessa `WebhookEvent` com `processado=False` e reconsulta status |
| `antiblock.tasks.advance_warmup_plans` | 03:00 diário | Avança um dia em cada plano de aquecimento |
| `webhooks.tasks.purge_old_webhook_events` | 03:30 diário | Apaga eventos processados com mais de 30 dias |

## Tasks sob demanda

| Task | Disparada por |
|---|---|
| `campaigns.tasks.dispatch_campaign` | Início/retomada de campanha; agenda um `send_campaign_contact` por contato com `countdown` cumulativo |
| `campaigns.tasks.send_campaign_contact` | Pela anterior; processa um contato |
| `webhooks.tasks.process_webhook_event` | Recebimento de webhook |
| `scripts.tasks.continue_after_delay` | Passo do tipo `delay` |
| `scripts.tasks.check_timeout` | Passo `aguardar_resposta`, agendada para `timeout_h` |
| `core.tasks.ping` | Diagnóstico manual: confirma que worker/beat executam |

## Como escrever uma task

Wrapper fino, com import do service dentro da função (evita carregar
models no import do módulo) e log em `chave=valor`:

```python
@shared_task
def advance_warmup_plans():
    from .services import advance_all_warmups

    total = advance_all_warmups()
    logger.info('advance_warmup_plans total=%s', total)
    return total
```

Tasks que operam sobre um objeto devem tolerar que ele não exista mais e
checar o estado antes de agir — elas podem rodar depois de o estado ter
mudado:

```python
cc = CampaignContact.objects.filter(id=campaign_contact_id).first()
if cc is None or cc.status != CampaignContact.STATUS_PENDENTE:
    return None
```
