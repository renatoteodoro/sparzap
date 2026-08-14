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
| Participantes do grupo | `GET /group/participants/{name}?groupJid=` | — | `EvolutionClient.fetch_all_participants` |
| Promover/remover admin | `POST /group/updateParticipant/{name}` | `{"groupJid": str, "action": "promote\|demote", "participants": [jid]}` | `EvolutionClient.update_participant` |
| Registrar webhook | `POST /webhook/set/{name}` | `{"webhook": {"url": str, "enabled": true, "events": [...]}}` | `EvolutionClient.set_webhook` |

## Eventos de webhook processados

`messages.upsert`, `messages.update`, `connection.update`, `contacts.upsert`
— ver `webhooks/services.py` (Sprint 3).

## Endpoints lentos (medido em conta real)

`fetchAllGroups` e `fetchAllParticipants` buscam metadados de **cada grupo,
um a um**, direto do WhatsApp. Numa conta real com 197 grupos a chamada leva
**~93 segundos**, de forma consistente — não há cache que ajude, o custo se
repete a cada chamada.

Consequências, já tratadas no código:

- Usam `TIMEOUT_LENTO` (180s) e **`retry=False`** em `instances/evolution.py`.
  O timeout padrão de 10s derrubava a sincronização sempre, e o retry
  automático de GET triplicava a espera sem chance real de sucesso.
- São chamados por **task Celery** (`contacts.tasks.sync_groups_task`,
  `extract_participants_task`), nunca direto na view: em produção o gunicorn
  mata o worker em 30s (default) e o Nginx devolve 504 em 60s.

## Divergências conhecidas entre versões da Evolution API

- **Participantes do grupo mudaram de caminho e de formato na v2.3.7**
  (confirmado contra instância real):
  - O caminho antigo `/group/fetchAllParticipants/{name}/{groupJid}` responde
    **404**. O correto é `/group/participants/{name}?groupJid=`.
  - A resposta é `{"participants": [...]}` e cada item traz o `id` como
    **LID** (`169397956132906@lid`) — identificador de privacidade do
    WhatsApp que **não contém o telefone**. O número real vem em
    `phoneNumber` (`554899072303@s.whatsapp.net`).
  - `contacts.services.extract_participants` prioriza `phoneNumber` e mantém
    o fallback para `id`/`jid` das versões antigas. Ler `id` direto faria a
    extração terminar com **zero contatos e nenhum erro**.
  - `admin` vem como `null`, `"admin"` ou `"superadmin"` (versões antigas
    mandavam `True`/`False`; o código trata qualquer valor preenchido como
    admin).

> **Regra de produto:** `extract_participants` **ignora admins e
> superadmins** — eles nunca viram `Contact` e portanto nunca entram no
> público de uma campanha. Reextrair um grupo também **desvincula** admins
> coletados antes da regra existir (o `Contact` não é apagado, pois pode ser
> membro comum de outro grupo). Isso é independente de `demote_self`, que
> continua agindo apenas sobre o próprio bot — o Sparzap não rebaixa
> ninguém.
- `sendMedia`/`sendWhatsAppAudio` aceitam tanto URL pública quanto base64;
  o Sparzap sempre envia URL (mídia servida por `MEDIA_URL`/S3 futuramente).

## Checklist do spike (Tarefa 0.5)

- [ ] 0.5.1 Validar `POST /message/sendText` com a instância `techteo` real
- [ ] 0.5.2 Validar recebimento de `messages.upsert` em endpoint de teste
- [ ] 0.5.3 Validar `GET /group/fetchAllParticipants` em grupo real
- [ ] 0.5.4 Validar `POST /group/updateParticipant` com `action=demote`
- [x] 0.5.5 Documentar os payloads (este arquivo) — a partir da doc oficial e do contrato do PRD; **pendente de confirmação com chamadas reais**
