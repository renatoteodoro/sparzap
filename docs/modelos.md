# Modelos de dados

Todos herdam de `core.models.BaseModel` (`created_at`, `updated_at`).
Campos listados são os relevantes para entender o domínio — para a
definição exata, veja o `models.py` de cada app.

## accounts

**`User`** — `AbstractBaseUser` + `PermissionsMixin`. Login por **e-mail**
(`USERNAME_FIELD = 'email'`), sem campo `username`. Criado por
`UserManager.create_user(email, password, ...)`.

Campos: `email` (único), `nome`, `is_staff`, `is_active`.

## instances

**`Instance`** — um número de WhatsApp conectado via Evolution API.
É o objeto central: campanhas, gatilhos e grupos dependem dele.

| Campo | Observação |
|---|---|
| `owner` | FK para `User` |
| `nome` | Nome amigável exibido no painel |
| `evolution_instance_name` | Slug único; é o identificador usado na Evolution API |
| `numero` | Preenchido pelo webhook `connection.update` |
| `status` | `desconectado` · `aguardando_qr` · `conectado` · `banido` |
| `limite_diario` | Teto de envios por dia (padrão 30). O aquecimento altera este campo |
| `janela_inicio` / `janela_fim` | Janela de operação (padrão 08:00–21:00), tipo `TimeField` |
| `ativo` | `False` = pausada; a auto-pausa do AntiBlock mexe aqui |

`pode_receber_disparo` → `ativo and status == conectado`.

**`InstanceEvent`** — histórico de mudança de status
(`status_anterior` → `status_novo` + `detalhe`). Gravado por
`instances.services.set_status`.

## webhooks

**`WebhookEvent`** — payload bruto recebido da Evolution.
Campos: `instance`, `evento`, `message_id` (indexado, usado para
deduplicação), `payload` (JSON), `processado`, `erro`.

Eventos processados com mais de 30 dias são expurgados por task periódica.

## contacts

| Model | O que é |
|---|---|
| `Contact` | Número em E.164 + nome. Único por (`owner`, `numero_e164`). Tem `opt_out` e `ultimo_contato` |
| `Tag` | Etiqueta do usuário, única por (`owner`, `nome`) |
| `ContactTag` | Tabela intermediária Contact↔Tag |
| `ContactList` | Lista nomeada de contatos (M2M direto) |
| `Group` | Grupo de WhatsApp sincronizado de uma instância. Único por (`instance`, `jid`). Tem `bot_e_admin` |
| `GroupMember` | Participante do grupo, ligado a um `Contact` |
| `AdminActionLog` | Registro do auto-demote (remover o próprio bot da administração do grupo antes do disparo) |

Números sempre passam por `contacts.utils.normalize_br_number`, que aceita
JID do WhatsApp, máscara `(11) 98765-4321`, com ou sem DDI, e adiciona o 9º
dígito quando aplicável.

## library

**`Message`** — item da biblioteca. `tipo` é `texto` · `audio` · `imagem` ·
`video` · `documento`; tipos não-texto exigem `midia` (validado em `clean()`).
`conteudo` aceita variáveis `{{nome}}`, `{{grupo}}`, `{{link}}`, `{{empresa}}`.

**`MessageVariant`** — variações de texto da mesma mensagem; uma é sorteada
a cada envio (`library.services.pick_variant`).

**`MessageFolder`** — pasta para organizar mensagens.

## scripts

**`Script`** — sequência nomeada de passos.

**`ScriptStep`** — um passo, ordenado por `ordem` (único por script).

| `tipo` | Campos usados |
|---|---|
| `mensagem` | `message` |
| `delay` | `delay_s` |
| `aguardar_resposta` | `timeout_h` (padrão 48) |
| `condicao` | `condicao_contem`, `proximo_passo` (destino se a condição casar), `usar_ia`/`ia_config`/`condicao_ia_descricao` (classificação por IA, opcional — cai em `condicao_contem` se falhar) |
| `mudar_etapa` | `etapa_destino` (nome da etapa no CRM) |
| `encerrar` | — (conclui o run; marca o fim de um ramo do funil) |

Um funil com dois ramos (condição → mensagem A / mensagem B) precisa de um
passo `encerrar` no fim do primeiro ramo. Sem ele, o passo de mensagem
avança para `ordem + 1` e o ramo de cima escorrega para dentro do ramo de
baixo, mandando as duas mensagens ao mesmo contato. Omitir o `encerrar` é o
que faz os dois ramos convergirem de propósito numa mensagem final comum.

**`ScriptRun`** — execução do script para um contato.
`status`: `em_andamento` · `aguardando_resposta` · `concluido` ·
`cancelado` · `erro`. `origem`: `teste` ou `campanha`.
Guarda `passo_atual`, `ultimo_message_id` e `contexto_extra` (JSON com as
variáveis disponíveis para renderizar a mensagem).

## ai

**`AIConfig`** — credencial de IA configurada por conta (dono), usada
pelo passo "condição" dos scripts quando `usar_ia` está ligado.

| Campo | Observação |
|---|---|
| `provider` | `anthropic` · `openai` · `gemini` · `openai_compativel` (URL própria, ex.: OpenCode Zen) |
| `modelo` | String livre — ex. `claude-opus-5`, `gpt-5`, `gemini-2.5-flash` |
| `api_key_cifrada` | Nunca em texto puro; acesse via a property `api_key` (cifra/decifra com Fernet, `ai.crypto`) |
| `base_url` | Só usado quando `provider = openai_compativel` |

`ai.services.classificar(config, descricao, texto)` retorna `True`/`False`
se a IA respondeu com sucesso, ou `None` se falhou — `scripts.services.
_resolve_condicao` cai no `condicao_contem` de sempre quando recebe `None`.

## campaigns

**`Campaign`** — disparo em massa.
`status`: `rascunho` · `agendada` · `em_andamento` · `pausada` ·
`concluida` · `cancelada`.

| Campo | O que faz |
|---|---|
| `instance` / `script` | Por onde envia e o que envia |
| `contatos_avulsos` / `grupos` | Definem o público (M2M) |
| `filtro_publico` | `todos` ou `nao_respondeu` |
| `antiduplicacao_dias` | Pula quem já recebeu campanha de mesmo nome nos últimos N dias (padrão 30) |
| `remover_admin_antes` | Dispara o auto-demote nos grupos antes de começar |

**`CampaignContact`** — um contato dentro de uma campanha. Único por
(`campaign`, `contact`). `status`: `pendente` · `enviada` · `respondida` ·
`falha` · `pulada`. Liga-se 1:1 ao `ScriptRun` criado para ele.

**`DeliveryLog`** — cada mudança de estado de entrega
(`enviada` · `entregue` · `lida` · `falha`) casada pelo `message_id` da
Evolution.

## antiblock

| Model | O que é |
|---|---|
| `DailyLimit` | Contador de envios por (`instance`, `data`). Incrementado com `select_for_update` |
| `RateSettings` | 1:1 com a instância: `intervalo_min_s` (20), `intervalo_max_s` (60), `fator_escalonamento`, `falhas_consecutivas` |
| `BlockEvent` | Registro de bloqueio. `motivo`: `rate_limit` · `falhas_consecutivas` · `desconectado` · `limite_diario` · `fora_janela`. `pausou_instancia` marca a auto-pausa |
| `WarmupPlan` | Plano de aquecimento: `dias_total` (14), `dia_atual`, `limite_final` (limite original, restaurado ao fim) |
| `WarmupActivity` | Limite aplicado em cada dia do plano |

O aquecimento funciona **alterando `Instance.limite_diario`** dia a dia —
não há checagem extra em `campaigns`, o `can_send` já barra pelo limite.

## triggers

**`Trigger`** — resposta automática por palavra-chave.
`palavras_chave` é uma string separada por vírgula; `modo` é `ou`
(qualquer palavra) ou `e` (todas). `prioridade` menor é avaliada primeiro.
Escopo opcional por `grupo` ou `contato`. `limite_repeticao_minutos`
(padrão 60) evita loop de resposta com o mesmo contato.

Ações possíveis: responder com uma `Message`, aplicar `etiqueta_nome`,
mover para `etapa_destino` no CRM, e agendar `followup_mensagem` após
`followup_apos_horas`.

**`TriggerLog`** — cada disparo, com as `acoes_executadas`.

**`ScheduledMsg`** — mensagem individual agendada (follow-up), distinta do
disparo em massa. `status`: `pendente` · `enviada` · `cancelada` · `falha`.
`origem`: `manual` ou `gatilho`.

## crm

**`Pipeline`** → **`Stage`** (ordenada, com `cor` e `e_final`) →
**`Lead`** (único por `contact` + `pipeline`).

`crm.services.get_or_create_default_pipeline` cria o pipeline padrão do
usuário sob demanda.

**`LeadNote`** — anotação; `automatica=True` quando gerada pelo sistema.

**`ConversationMessage`** — histórico da conversa do lead, com `direcao`
`entrada` ou `saida`.

## reports

**`Backup`** — snapshot JSON da configuração do usuário (mensagens,
scripts, gatilhos, pipelines, campanhas). `tipo` é `completo` ou
`seletivo`; `secoes` guarda o que foi incluído.
