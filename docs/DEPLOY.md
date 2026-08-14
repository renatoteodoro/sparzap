# Deploy em produção (VPS Ubuntu)

> ⚠️ Este guia foi escrito e revisado, mas **não foi executado contra uma VPS
> real** neste ambiente de desenvolvimento (sem acesso SSH/Docker a um
> servidor). Trate os passos abaixo como o plano de deploy a validar na
> primeira execução real — ver checklist ao final.

## Pré-requisitos na VPS

- Docker Engine + Docker Compose plugin já instalados.
- A Evolution API já rodando via Docker, com **PostgreSQL** e **Redis**
  próprios num `docker-compose` existente — o Sparzap **reaproveita** esse
  Postgres/Redis (não sobe os seus), então precisa entrar na mesma rede
  Docker. Descubra o nome dela com:
  ```bash
  docker network ls | grep evolution
  ```
  e configure `EVOLUTION_NETWORK_NAME` no `.env` com esse nome.
- Um banco `sparzap` criado nesse Postgres compartilhado:
  ```bash
  docker exec -it <container_postgres> psql -U postgres -c "CREATE DATABASE sparzap;"
  docker exec -it <container_postgres> psql -U postgres -c "CREATE USER sparzap WITH PASSWORD 'troque-esta-senha';"
  docker exec -it <container_postgres> psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE sparzap TO sparzap;"
  ```
- Um Redis DB separado do usado pela Evolution — use `CELERY_BROKER_URL=redis://<host-redis>:6379/2`
  (índices `0`/`1` costumam já estar em uso; confirme com quem administra a VPS).

## Passo a passo (primeira vez)

```bash
git clone <repo> sparzap && cd sparzap
cp .env.example .env
# edite o .env: SECRET_KEY forte, DEBUG=False, ALLOWED_HOSTS e
# CSRF_TRUSTED_ORIGINS com o domínio real, DB_ENGINE=postgresql com as
# credenciais criadas acima, CELERY_BROKER_URL/RESULT_BACKEND apontando
# para o Redis compartilhado, EVOLUTION_* com a apikey real,
# EVOLUTION_WEBHOOK_BASE_URL=https://seu-dominio (para os webhooks
# registrados automaticamente já saírem certos), EVOLUTION_NETWORK_NAME.

docker compose -f docker-compose.prod.yml --env-file .env build
docker compose -f docker-compose.prod.yml --env-file .env run --rm web python manage.py migrate
docker compose -f docker-compose.prod.yml --env-file .env run --rm web python manage.py createsuperuser
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

Confirme que os 4 serviços subiram saudáveis:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 web worker beat nginx
```

## HTTPS

Duas opções:

1. **Certbot na própria VPS**, apontando o certificado gerado para
   `deploy/certs/fullchain.pem` e `deploy/certs/privkey.pem`, depois
   descomentar o bloco `server { listen 443 ssl; ... }` em `deploy/nginx.conf`
   e comentar o `return 301` no bloco 80 para forçar redirecionamento.
2. **Outro proxy/terminador TLS já existente na VPS** (ex.: um Traefik ou
   Nginx compartilhado na frente de todos os serviços) — nesse caso, deixe o
   `nginx` deste projeto só em HTTP interno e aponte o proxy externo para a
   porta 80 dele.

## Apontar o webhook da Evolution para a URL pública

Instâncias criadas **depois** do deploy já registram o webhook sozinhas
(`instances.services.provision_instance` usa `EVOLUTION_WEBHOOK_BASE_URL`).
Para instâncias que já existiam antes, refaça o registro manualmente:

```bash
curl -X POST http://localhost:8080/webhook/set/<nome-da-instancia> \
  -H "apikey: <EVOLUTION_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"webhook": {"url": "https://seu-dominio/webhooks/evolution/<nome-da-instancia>/?token=<EVOLUTION_WEBHOOK_SECRET>", "enabled": true, "events": ["MESSAGES_UPSERT","MESSAGES_UPDATE","CONNECTION_UPDATE","CONTACTS_UPSERT"]}}'
```

## Backup do banco (dump periódico)

`deploy/backup-db.sh` gera um dump comprimido do Postgres compartilhado com
retenção configurável. Rode no **host** da VPS (não dentro de um container do
Sparzap) via cron:

```bash
crontab -e
# todo dia às 4h da manhã:
0 4 * * * DB_CONTAINER=postgres DB_NAME=sparzap DB_USER=sparzap /caminho/para/sparzap/deploy/backup-db.sh >> /var/log/sparzap-backup.log 2>&1
```

## Healthcheck e alertas

- `GET /healthz/` — verifica banco, broker do Celery e a Evolution API; retorna
  `200` (`status: ok`) ou `503` (`status: degraded`) com o detalhe de cada
  checagem. Use num monitor externo (UptimeRobot, cron+curl, etc.).
- Alertas operacionais (instância desconectada, campanha pausada
  automaticamente pelo AntiBlock, taxa de falha alta numa campanha, fila do
  Celery acumulada) vão para o log estruturado (JSON em produção) e,
  opcionalmente, para um webhook configurado em `ALERT_WEBHOOK_URL` (Slack/
  Discord/genérico) — ver `core/alerts.py`.

## Atualizações subsequentes

```bash
./deploy/update.sh
```

Faz `git pull` → rebuild das imagens → `migrate` → `up -d` com o mínimo de
downtime (só recria os containers cujo build mudou).

## Troubleshooting

| Sintoma | Causa provável | O que checar |
|---|---|---|
| `web` reinicia em loop | Erro de configuração no `.env` (SECRET_KEY, DB) | `docker compose logs web` |
| Webhook nunca chega | `EVOLUTION_WEBHOOK_BASE_URL` errado, ou Sparzap não está na mesma rede da Evolution | `docker network inspect <rede>`; confira se `web` aparece nela |
| `502 Bad Gateway` no Nginx | `web` ainda subindo ou caiu | `docker compose ps`, `docker compose logs web` |
| Migração falha com "role does not exist" | Usuário/banco Postgres não criados no host compartilhado | Repetir os `CREATE DATABASE`/`CREATE USER` acima |
| Estáticos (CSS/JS) não carregam | `collectstatic` não rodou no build, ou `STATIC_URL` divergente | Confirme que o build do `Dockerfile` chegou até `collectstatic` sem erro |

## Checklist de primeira execução real (pendente de validar contra a VPS)

- [ ] `docker compose build` conclui sem erro na VPS real
- [ ] `migrate` aplica todas as migrações contra o Postgres compartilhado
- [ ] Os 4 serviços (`web`, `worker`, `beat`, `nginx`) ficam saudáveis
- [ ] HTTPS funcionando com certificado válido
- [ ] Webhook da Evolution chega em `/webhooks/evolution/<instancia>/`
- [ ] Uso de RAM com tudo de pé cabe na VPS (1.8 GB + swap) — monitorar com `docker stats`
