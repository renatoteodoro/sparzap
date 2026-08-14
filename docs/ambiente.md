# Ambiente de desenvolvimento

## Subir o projeto

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

Com o `.env` padrão o projeto sobe **sem PostgreSQL e sem Redis**: usa
SQLite e roda as tasks do Celery de forma síncrona
(`CELERY_TASK_ALWAYS_EAGER=True`). Ver as ressalvas em
[tarefas-assincronas.md](tarefas-assincronas.md).

Python 3.12+ (a imagem Docker usa `python:3.12-slim`).

## Evolution API local (opcional)

Para testar conexão de WhatsApp por QR Code de verdade, existe um compose
separado que sobe uma Evolution API com Postgres e Redis próprios:

```bash
docker compose -f docker-compose.evolution-local.yml up -d
```

Ela fica em `http://localhost:8080` com a apikey definida no próprio
arquivo. Ajuste `EVOLUTION_API_KEY` no seu `.env` para o mesmo valor.

> ⚠️ **`EVOLUTION_WEBHOOK_BASE_URL` não pode ser `localhost`** quando a
> Evolution roda em container: ali `localhost` é o próprio container, não a
> sua máquina, e os webhooks nunca chegam (o sintoma é o status da instância
> ficar preso em "aguardando QR" mesmo com o celular conectado). No Docker
> Desktop use `http://host.docker.internal:8000` e inclua
> `host.docker.internal` em `ALLOWED_HOSTS`.

## Variáveis do `.env`

### Django

| Variável | Padrão | Para quê |
|---|---|---|
| `SECRET_KEY` | chave de dev | Chave criptográfica do Django. Obrigatório trocar em produção. |
| `DEBUG` | `True` | Em `False` liga cookies seguros, proxy SSL header e log JSON. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts aceitos. Em dev, `testserver` é adicionado automaticamente. |
| `CSRF_TRUSTED_ORIGINS` | vazio | Domínio público com esquema (`https://...`) quando atrás de proxy. |
| `SECURE_SSL_REDIRECT` | `False` | Só tem efeito com `DEBUG=False`. Ligue depois do HTTPS funcionando. |
| `SECURE_HSTS_SECONDS` | `0` | Idem — ligue só com certificado válido. |

### Banco

| Variável | Padrão | Para quê |
|---|---|---|
| `DB_ENGINE` | `sqlite3` | `postgresql` para usar Postgres; qualquer outro valor cai no SQLite. |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | `sparzap` / `sparzap` / vazio / `localhost` / `5432` | Só usados com `DB_ENGINE=postgresql`. |

### Celery

| Variável | Padrão | Para quê |
|---|---|---|
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Broker. |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Backend de resultado. |
| `CELERY_TASK_ALWAYS_EAGER` | `True` no `.env.example` | `True` = tasks rodam síncronas, sem broker. Só para desenvolvimento. |

### Evolution API

| Variável | Padrão | Para quê |
|---|---|---|
| `EVOLUTION_BASE_URL` | `http://localhost:8080` | Base da Evolution API. |
| `EVOLUTION_API_KEY` | vazio | Header `apikey` de toda chamada. |
| `EVOLUTION_WEBHOOK_SECRET` | placeholder | Token na querystring do webhook; se não bater, a requisição é rejeitada com 403. |
| `EVOLUTION_WEBHOOK_BASE_URL` | `http://localhost:8000` | URL onde a Evolution alcança o Sparzap. Ver o aviso acima. |

### Produção e operação

| Variável | Padrão | Para quê |
|---|---|---|
| `EVOLUTION_NETWORK_NAME` | `evolution_default` | Rede Docker externa onde já rodam Postgres/Redis/Evolution na VPS. |
| `ALERT_WEBHOOK_URL` | vazio | Webhook (Slack/Discord/genérico) que recebe os alertas operacionais. Vazio = só log. |

## Comandos do dia a dia

```bash
.venv\Scripts\python manage.py runserver
.venv\Scripts\python manage.py makemigrations
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py test
.venv\Scripts\python -m flake8
```

Com broker real, o worker e o agendador sobem em processos separados:

```bash
.venv\Scripts\celery -A core worker -l info
.venv\Scripts\celery -A core beat -l info
```

## Healthcheck

`GET /healthz/` devolve o estado de banco, broker e Evolution API.
Retorna `200` (`status: ok`) ou `503` (`status: degraded`). A Evolution fora
do ar aparece no detalhe, mas não derruba o healthcheck sozinha.
