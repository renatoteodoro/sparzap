# Sparzap ⚡

**Automação de vendas e divulgação no WhatsApp** — Django + Evolution API.

Disparo em massa com protocolo anti-banimento, scripts de 2+ mensagens,
gatilhos inteligentes, etapas/CRM e aquecedor de número. Servidor próprio 24/7
(sem extensão de browser), multi-número nativo.

> 📄 Documento de produto e roadmap de sprints: [PRD.md](PRD.md)
> 📚 Documentação técnica (arquitetura, padrões, modelos, testes): [docs/](docs/README.md)

## Desenvolvimento local

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt   # inclui coverage/flake8/black/isort
copy .env.example .env
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

Por padrão o `.env` usa SQLite e `CELERY_TASK_ALWAYS_EAGER=True` — o projeto
sobe sem precisar de PostgreSQL/Redis rodando localmente (tasks do Celery
executam de forma síncrona). Para se aproximar de produção, configure
`DB_ENGINE=postgresql` e um `CELERY_BROKER_URL` real no `.env`.

## Testes

```bash
# Suíte completa
.venv\Scripts\python manage.py test

# Um app específico
.venv\Scripts\python manage.py test antiblock

# Com cobertura (mede o app inteiro, exclui migrations/tests)
.venv\Scripts\python -m coverage run --source=. --omit=".venv/*,*/migrations/*,manage.py,*/tests.py" manage.py test
.venv\Scripts\python -m coverage report
```

Todos os testes usam `EvolutionClient` mockado — nenhum teste chama a Evolution
API real. Fixtures reutilizáveis ficam em `core/factories.py`.

## Qualidade de código

```bash
.venv\Scripts\python -m flake8      # lint
.venv\Scripts\python -m black .     # formatação
.venv\Scripts\python -m isort .     # ordenação de imports
```

Configuração em `setup.cfg` (flake8/isort) e `pyproject.toml` (black).
