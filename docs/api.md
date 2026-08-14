# REST API do Sparzap

Base: `/api/` · Autenticação: Token (`Authorization: Token <chave>`)
Documentação interativa (Swagger): `/api/schema/docs/` · Schema OpenAPI: `/api/schema/`

Todos os endpoints são isolados por usuário — você só vê/edita os seus próprios dados.
Rate limit padrão: 120 requisições/minuto por token.

## Obter um token

```bash
curl -X POST http://localhost:8000/api/token/ \
  -d "username=voce@empresa.com&password=sua-senha"
```

> Não há uma tela no painel para gerar/revogar o token pelo navegador ainda —
> use este endpoint ou o Django Admin (`Tokens` em `Auth Token`).

## Instâncias

```bash
curl http://localhost:8000/api/instances/ \
  -H "Authorization: Token SEU_TOKEN"
```

Retorna status, `limite_diario` e se está `ativo` — somente leitura.

## Campanhas

```bash
# Listar
curl http://localhost:8000/api/campaigns/ -H "Authorization: Token SEU_TOKEN"

# Criar
curl -X POST http://localhost:8000/api/campaigns/ \
  -H "Authorization: Token SEU_TOKEN" \
  -d "nome=Campanha via API&instance=1&script=1"

# Disparar uma campanha existente (em rascunho ou pausada)
curl -X POST http://localhost:8000/api/campaigns/1/start/ -H "Authorization: Token SEU_TOKEN"

# Relatório em tempo real (pendente/enviada/respondida/falha)
curl http://localhost:8000/api/campaigns/1/report/ -H "Authorization: Token SEU_TOKEN"
```

## Contatos

```bash
curl -X POST http://localhost:8000/api/contacts/ \
  -H "Authorization: Token SEU_TOKEN" \
  -d "numero_e164=11988887777&nome=Fulano"
```

O número é normalizado automaticamente para E.164 (`+5511988887777`).
Se o número já existir para o seu usuário, os dados são atualizados (upsert).

## Agendar uma mensagem (follow-up)

```bash
curl -X POST http://localhost:8000/api/messages/schedule/ \
  -H "Authorization: Token SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"numero": "11977776666", "instance_id": 1, "message_id": 3, "data_hora": "2026-09-01T14:00:00Z"}'
```

## Leads

```bash
curl http://localhost:8000/api/leads/ -H "Authorization: Token SEU_TOKEN"
```

Retorna cada lead com `etapa` (nome da etapa atual) e `origem` — somente leitura.

## Erros

| Status | Significado |
|---|---|
| 401 | Token ausente ou inválido |
| 403 | Autenticado, mas sem permissão sobre o recurso |
| 404 | Recurso não encontrado (ou pertence a outro usuário) |
| 429 | Rate limit excedido (120/min) |
