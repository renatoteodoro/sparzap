# Integração com a Evolution API — notas do spike (Sprint 0, Tarefa 0.5)

> **Status:** ⚠️ validação estrutural feita a partir da documentação e do
> contrato já registrado no PRD.md (seção 8.5); a validação **ao vivo** contra
> a instância `techteo` da VPS (0.5.1–0.5.4) **não foi executada** neste
> ambiente de desenvolvimento — não há rede até a VPS nem `EVOLUTION_API_KEY`
> real disponível aqui. `instances/evolution.py` (Sprint 2) foi implementado
> contra este contrato; rodar `python manage.py test_evolution_connection`
> (ou o teste de instância pelo painel) na primeira execução em produção para
> confirmar payloads reais e ajustar o client se necessário.

## Autenticação

Toda chamada usa o header `apikey: <EVOLUTION_API_KEY>` sobre a base
`EVOLUTION_BASE_URL` (`http://localhost:8080` na VPS, porta interna do
container Evolution).

## Endpoints usados pelo Sparzap

| Ação | Método/Endpoint | Payload | Uso no código |
|---|---|---|---|
| Criar instância | `POST /instance/create` | `{"instanceName": str, "qrcode": true, "integration": "WHATSAPP-BAILEYS"}` | `EvolutionClient.create_instance` |
| Conectar (QR) | `GET /instance/connect/{name}` | — | `EvolutionClient.connect` |
| Status | `GET /instance/connectionState/{name}` | — | `EvolutionClient.connection_state` |
| Deletar instância | `DELETE /instance/delete/{name}` | — | `EvolutionClient.delete_instance` |
| Enviar texto | `POST /message/sendText/{name}` | `{"number": str, "text": str}` | `EvolutionClient.send_text` |
| Enviar mídia | `POST /message/sendMedia/{name}` | `{"number": str, "mediatype": "image\|video\|document", "media": url_ou_base64, "caption": str}` | `EvolutionClient.send_media` |
| Enviar áudio | `POST /message/sendWhatsAppAudio/{name}` | `{"number": str, "audio": url_ou_base64}` | `EvolutionClient.send_audio` |
| Mencionar todos | `POST /group/sendMention/{name}` | `{"groupJid": str, "text": str}` | `EvolutionClient.send_mention` |
| Listar grupos | `GET /group/fetchAllGroups/{name}?getParticipants=false` | — | `EvolutionClient.fetch_all_groups` |
| Participantes do grupo | `GET /group/fetchAllParticipants/{name}/{groupJid}` (ou `?groupJid=`, variação de versão) | — | `EvolutionClient.fetch_all_participants` |
| Promover/remover admin | `POST /group/updateParticipant/{name}` | `{"groupJid": str, "action": "promote\|demote", "participants": [jid]}` | `EvolutionClient.update_participant` |
| Registrar webhook | `POST /webhook/set/{name}` | `{"webhook": {"url": str, "enabled": true, "events": [...]}}` | `EvolutionClient.set_webhook` |

## Eventos de webhook processados

`messages.upsert`, `messages.update`, `connection.update`, `contacts.upsert`
— ver `webhooks/services.py` (Sprint 3).

## Divergências conhecidas entre versões da Evolution API

- O formato exato de `fetchAllParticipants` varia entre v2.x (`GET` com
  `groupJid` na URL vs. querystring) — `EvolutionClient` tenta o formato de
  path primeiro; ajustar se a instância real responder 404.
- `sendMedia`/`sendWhatsAppAudio` aceitam tanto URL pública quanto base64;
  o Sparzap sempre envia URL (mídia servida por `MEDIA_URL`/S3 futuramente).

## Checklist do spike (Tarefa 0.5)

- [ ] 0.5.1 Validar `POST /message/sendText` com a instância `techteo` real
- [ ] 0.5.2 Validar recebimento de `messages.upsert` em endpoint de teste
- [ ] 0.5.3 Validar `GET /group/fetchAllParticipants` em grupo real
- [ ] 0.5.4 Validar `POST /group/updateParticipant` com `action=demote`
- [x] 0.5.5 Documentar os payloads (este arquivo) — a partir da doc oficial e do contrato do PRD; **pendente de confirmação com chamadas reais**
