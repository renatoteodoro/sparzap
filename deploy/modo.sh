#!/usr/bin/env bash
# Alterna esta máquina entre o modo de desenvolvimento e a simulação de
# produção. Os dois usam o MESMO SQLite e a MESMA Evolution, então não podem
# rodar ao mesmo tempo: o webhook da Evolution aponta para um endereço só.
#
#   ./deploy/modo.sh prod     sobe os containers (nginx:80 + gunicorn + worker + beat)
#   ./deploy/modo.sh dev      derruba os containers e prepara o runserver (:8000)
#   ./deploy/modo.sh status   mostra o que está rodando agora
#
# No Windows, rode pelo Git Bash.
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.prod.yml -f docker-compose.prod-local.yml --env-file .env.prod"
PY=".venv/Scripts/python"
[ -x "$PY" ] || PY=".venv/bin/python"

registrar_webhooks() {
    # A Evolution guarda a URL de webhook de quando a instância foi criada.
    # Trocar de modo muda o endereço do Sparzap (:8000 no dev, :80 no nginx),
    # e sem reescrever o registro as respostas do WhatsApp somem sem erro.
    echo "-> reapontando os webhooks da Evolution"
    if [ "$1" = "prod" ]; then
        $COMPOSE exec -T web python manage.py registrar_webhooks
    else
        "$PY" manage.py registrar_webhooks
    fi
}

case "${1:-}" in
    prod)
        echo "== simulação de produção =="
        docker start sparzap-celery-redis >/dev/null 2>&1 || true
        $COMPOSE up -d --build
        echo "-> aguardando o web subir"
        for _ in $(seq 1 30); do
            if curl -fsS -o /dev/null http://localhost/healthz/ 2>/dev/null; then break; fi
            sleep 2
        done
        registrar_webhooks prod
        echo
        echo "pronto: http://localhost/"
        echo "logs:   docker compose -f docker-compose.prod.yml -f docker-compose.prod-local.yml logs -f web worker beat"
        echo "NOTA:   o beat roda as periódicas de verdade — o aquecimento altera o limite_diario das instâncias."
        ;;

    dev)
        echo "== desenvolvimento =="
        $COMPOSE down
        docker start sparzap-celery-redis >/dev/null 2>&1 || true
        registrar_webhooks dev
        echo
        echo "containers de produção derrubados. Agora suba, em dois terminais:"
        echo "  $PY manage.py runserver 0.0.0.0:8000"
        echo "  .venv/Scripts/celery -A core worker -l info --pool=solo"
        echo
        echo "(o .env de dev precisa estar com EVOLUTION_WEBHOOK_BASE_URL na porta 8000)"
        ;;

    status)
        echo "== containers =="
        docker ps --filter "name=sparzap" --format "  {{.Names}}\t{{.Status}}\t{{.Ports}}"
        echo "== portas =="
        for p in 80 8000 8080; do
            if curl -fsS -o /dev/null --max-time 2 "http://localhost:$p/" 2>/dev/null; then
                echo "  $p: respondendo (HTTP)"
            else
                echo "  $p: sem resposta"
            fi
        done
        # Redis não fala HTTP — testa a porta, não o protocolo.
        if docker exec sparzap-celery-redis redis-cli ping >/dev/null 2>&1; then
            echo "  6380: redis respondendo (PONG)"
        else
            echo "  6380: redis sem resposta"
        fi
        echo "== webhook registrado na Evolution (instância 'pessoal') =="
        curl -fsS --max-time 5 "http://localhost:8080/webhook/find/pessoal" \
            -H "apikey: ${EVOLUTION_API_KEY:-dev-local-apikey-troque-se-quiser}" 2>/dev/null \
            | sed -n 's/.*"url":"\([^"]*\)".*/  \1/p' || echo "  (Evolution não respondeu)"
        ;;

    *)
        echo "uso: $0 {prod|dev|status}" >&2
        exit 2
        ;;
esac
