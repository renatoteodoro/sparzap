# Runbook de incidentes — Sparzap

> Guia rápido para os incidentes mais prováveis em produção. Ver também
> `docs/DEPLOY.md` (troubleshooting de deploy) e `docs/evolution.md`
> (contrato da integração).

## Número banido / instância banida

**Sintomas:** `Instance.status = banido`, alerta `instancia_desconectada` no
log/webhook, envios da instância param.

1. Confirme no painel do WhatsApp Business (ou no app do número) se o número
   foi banido de verdade ou apenas desconectado.
2. Verifique `AdminActionLog` e `BlockEvent` da instância — quantas falhas
   consecutivas houve antes do banimento? Confirma se o limite diário/janela
   estavam configurados de forma conservadora (Sprint 7/13).
3. **Não** tente reconectar o mesmo número imediatamente com um limite alto —
   se for reativado, inicie um novo plano de aquecimento (`antiblock:warmup`)
   do zero.
4. Se o número for definitivamente perdido: crie uma nova `Instance` com um
   chip novo, aqueça por 14 dias antes de qualquer disparo grande.
5. Pausar campanhas que dependiam dessa instância (`campaigns:pause`) para
   não acumular `CampaignContact` em `falha`.

## Evolution API fora do ar

**Sintomas:** `/healthz/` reporta `evolution: indisponível`; `EvolutionUnavailable`
nos logs; QR code não carrega; disparos falham em lote.

1. Confirme se o container da Evolution está de pé na VPS:
   `docker ps | grep evolution`.
2. Veja os logs da Evolution (`docker logs <container_evolution>`) — problema
   de banco/Redis compartilhado costuma aparecer lá primeiro.
3. Enquanto a Evolution estiver fora, o Sparzap **não trava**: `dispatch()`
   levanta `EvolutionUnavailable`, o AntiBlock registra a falha e, após 5
   falhas consecutivas por instância, pausa automaticamente (`BlockEvent`)
   para não acumular erro sem parar.
4. Depois que a Evolution voltar: reative manualmente as instâncias que
   foram auto-pausadas (`instances:list` → editar → reativar) e retome as
   campanhas pausadas.
5. Rode a reconciliação manualmente se suspeitar de webhooks perdidos durante
   a queda: `webhooks.tasks.reconcile_missed_webhooks.delay()` (ou espere o
   agendamento automático de 15 em 15 min).

## Fila do Celery travada/acumulando

**Sintomas:** alerta `fila_celery_acumulada`; campanhas não avançam; tasks
demoram para rodar.

1. Confirme se o worker está de pé: `docker compose -f docker-compose.prod.yml ps worker`.
2. Veja os logs do worker — uma task travada (ex.: chamada de rede sem
   timeout) segura o worker inteiro se a concorrência (`--concurrency`)
   estiver baixa.
3. Reinicie o worker: `docker compose -f docker-compose.prod.yml restart worker`.
4. Se o problema for volume real de campanhas simultâneas, considere subir
   `--concurrency` no `docker-compose.prod.yml` (linha `command` do serviço
   `worker`) ou separar filas por prioridade (não implementado ainda — ver
   PRD.md, possível item de roadmap).
5. Depois de resolvido, confirme que `core.tasks.check_queue_size` volta a
   reportar um valor abaixo do limiar (`LIMIAR_FILA`, hoje 500).

## Campanha com taxa de falha alta

**Sintomas:** alerta `campanha_taxa_falha_alta`.

1. Abra a campanha (`campaigns:detail`) e veja a coluna de status dos
   `CampaignContact` com `falha` — o campo `erro` de cada um explica o motivo
   (geralmente `AntiBlockBlocked` por instância desconectada, ou erro da
   Evolution).
2. Se o motivo for a instância caída: pause a campanha, resolva a instância,
   retome.
3. Se o motivo for número inválido/formatação: corrija a lista de contatos e
   crie uma nova campanha (não há reenvio automático para `falha`).

## Webhook não está chegando

Ver `docs/DEPLOY.md` → seção "Apontar o webhook da Evolution para a URL
pública" e a tabela de troubleshooting.
