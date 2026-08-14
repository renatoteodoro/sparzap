#!/usr/bin/env bash
# Atualização com o mínimo de downtime: git pull -> build -> migrate -> restart.
# Rodar a partir da raiz do repo, na VPS: ./deploy/update.sh
set -euo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env"

echo "==> git pull"
git pull --ff-only

echo "==> build das imagens"
$COMPOSE build

echo "==> aplicando migrações"
$COMPOSE run --rm web python manage.py migrate --noinput

echo "==> subindo os serviços (recria só o que mudou)"
$COMPOSE up -d --remove-orphans

echo "==> status"
$COMPOSE ps

echo "==> últimas linhas de log do web (Ctrl+C para sair)"
$COMPOSE logs --tail=50 -f web
