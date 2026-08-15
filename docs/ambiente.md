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

## Celery de verdade (opcional)

O modo eager esconde o comportamento real das tasks — principalmente o
intervalo entre mensagens de uma campanha. Para exercitar o ritmo de fato:

```bash
# Redis dedicado do Sparzap. O da Evolution não serve: não expõe porta para
# o host e usa o db 0 para o cache dela.
docker run -d --name sparzap-celery-redis -p 6380:6379 --restart unless-stopped redis:7-alpine
```

No `.env`:

```
CELERY_BROKER_URL=redis://localhost:6380/0
CELERY_RESULT_BACKEND=redis://localhost:6380/1
CELERY_TASK_ALWAYS_EAGER=False
```

E o worker (no Windows, `--pool=solo`; o pool padrão não funciona bem lá):

```bash
.venv\Scripts\celery -A core worker -l info --pool=solo
.venv\Scripts\celery -A core beat -l info    # só se quiser as tarefas periódicas
```

⚠️ Com o broker real, **se o worker cair os webhooks param de ser processados
em silêncio** — ficam enfileirados. Se as respostas do WhatsApp pararem de
surtir efeito, o worker é o primeiro lugar a olhar.

⚠️ O **beat** executa as periódicas de verdade, e o aquecimento **altera o
`limite_diario` das instâncias** dia a dia. Suba-o só quando quiser esse
comportamento.

## Simular produção na sua máquina

`deploy/modo.sh` alterna entre o `runserver` e o stack de produção
(gunicorn + worker + beat + nginx, `DEBUG=False`) em containers:

```bash
./deploy/modo.sh prod      # sobe os containers; app em http://localhost/
./deploy/modo.sh dev       # derruba os containers e prepara o runserver
./deploy/modo.sh status    # o que está rodando e para onde o webhook aponta
```

Os dois modos usam o mesmo banco e a mesma Evolution, então **não podem rodar
ao mesmo tempo**: o webhook da Evolution aponta para um endereço só (`:8000`
no runserver, `:80` no nginx). O script reaponta automaticamente via
`manage.py registrar_webhooks`; trocar de modo sem isso faz as respostas do
WhatsApp sumirem sem erro nenhum.

Diferente do `runserver`, **mudança de código exige rebuild da imagem** —
`docker compose ... restart` reinicia o container com o código antigo. O
`modo.sh prod` já faz `--build`.

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

⚠️ Em modo eager o `countdown` das tasks é **ignorado**: uma campanha dispara
todas as mensagens de uma vez, sem o intervalo anti-banimento de 20–60s. Para
ver o ritmo real, use um broker de verdade (seção abaixo).

A suíte de testes **não** depende dessa variável — `core/test_runner.py` força
o modo eager independente do `.env` (ver [testes.md](testes.md)).

### IA

| Variável | Padrão | Para quê |
|---|---|---|
| `AI_FIELD_ENCRYPTION_KEY` | derivada do `SECRET_KEY` | Chave Fernet que cifra as API keys dos provedores de IA em repouso (`ai.crypto`). |

Gere uma com:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Sem a variável, o valor é derivado do `SECRET_KEY` — conveniente em dev, mas
**trocar o `SECRET_KEY` torna as API keys já gravadas indecifráveis**. Em
produção defina uma chave própria e trate como segredo permanente.

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
