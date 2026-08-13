# PRD — WhatsApp Automator (Revzap-like)

> **Produto:** Plataforma web de automação de vendas/divulgação no WhatsApp
> **Inspiração:** Revzap (revzap.com.br) — features mapeadas do site oficial + vídeo 3
> **Stack:** Django (backend + admin) + Evolution API v2 (canal WhatsApp/Baileys) + Redis/Celery (fila) + PostgreSQL
> **Autor:** TechTeo (Renato Teodoro)
> **Status:** Draft — v0.1
> **Data:** 2026-08-13

---

## 1. Visão Geral

### 1.1 Problema
Divulgar ofertas/produtos em massa no WhatsApp manualmente é lento, sujeito a
erros e a banimento (spam). Ferramentas como a Revzap resolvem, mas são
extensões de Chrome acopladas ao WhatsApp Web (frágil, por conta), com assinatura
mensal e dependência de terceiros.

### 1.2 Solução
Aplicação web própria (SaaS interno → produto) que automatiza:
- Disparo em massa com **protocolo anti-banimento** (intervalos dinâmicos, limites diários)
- **Scripts de 2+ mensagens** com gatilho por resposta (ex: msg 1 induz resposta → msg 2 com link)
- **Gatilhos inteligentes** (resposta automática por palavra-chave)
- **Etapas/CRM** de lead (novo → contatado → respondeu → interessado → vendido)
- Mensagens rápidas (texto, áudio, mídia, documento)
- Organização por pastas, menção em grupos, exportação de contatos
- Múltiplos números/instâncias via Evolution API

### 1.3 Diferencias vs Revzap
| Revzap | Nosso produto |
|---|---|
| Extensão Chrome (WhatsApp Web) | **Servidor próprio** (Evolution API/Baileys) — roda 24/7 sem browser aberto |
| Conta pessoal em risco | **Números dedicados** por instância (chips separados) |
| Assinatura paga | Custo só de infra (VPS + chips) |
| Funciona só com browser aberto | API + fila + agendamento nativo |
| Black-box | Código próprio, extensível, integrável (ex: conectar ao pipeline Promo) |

---

## 2. Público-alvo e Casos de Uso

| Persona | Caso de uso |
|---|---|
| Afiliado (Renato / Promo Galáxias) | Disparar convites de grupo + ofertas com protocolo seguro |
| Pequeno vendedor | Nutrir leads, responder automaticamente, CRM simples |
| Prestador de serviços (TechTeo) | Atendimento + follow-up automático |
| (Futuro) Clientes do SaaS | Multi-tenant com planos |

**Caso de uso primário (v1):** o fluxo do vídeo 3 — entrar em grupos de
concorrentes → disparo em 2 passos (msg 1 induz resposta → msg 2 link) →
membros entram no grupo de ofertas.

---

## 3. Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                     Django App (Web)                     │
│  Painel (dashboard)  ·  Admin  ·  API REST (DRF)         │
└──────────┬──────────────────────────────┬────────────────┘
           │                              │
    ┌──────▼───────┐              ┌───────▼────────┐
    │  PostgreSQL   │              │ Redis + Celery │
    │  (dados)      │              │ (fila/agenda)  │
    └───────────────┘              └───────┬────────┘
                                           │
                              ┌────────────▼────────────┐
                              │   Evolution API (v2)     │
                              │  instância(s) Baileys    │
                              └────────────┬────────────┘
                                           │
                                    ┌──────▼──────┐
                                    │   WhatsApp   │
                                    │ (nº dedicado)│
                                    └─────────────┘
```

### Componentes
- **Django 5** + Django REST Framework: modelo de dados, API, painel (HTMX ou Vue leve)
- **Celery + Redis**: fila de envios, agendamento, retry
- **Evolution API v2.3.7** (já rodando na VPS, porta 8080, Docker): canal WhatsApp via Baileys — multi-instância, webhook de eventos, envio de texto/mídia
- **PostgreSQL**: persistência (a Evolution já tem postgres/redis Docker no host)
- **APScheduler ou Celery beat**: agendamento

### Fluxo de um disparo
1. Usuário cria **Campanha** (título, instância, script, público)
2. Usuário seleciona **Público** (grupos importados OU contatos importados)
3. Disparo entra na **fila** (Celery)
4. Worker processa cada contato com **delay dinâmico** (anti-ban)
5. Script: envia msg 1 → aguarda resposta (webhook) → envia msg 2
6. Estado do lead atualiza no **CRM/etapas** em tempo real

---

## 4. Funcionalidades (por módulo)

### 4.1 Instâncias / Números
- CRUD de instâncias da Evolution (nome, token, QR para pareamento)
- Status: conectado / desconectado / aguardando QR / banido
- **Limite de envio por número por dia** (configurável — anti-ban)
- **Aquecimento** (ver 4.7)

### 4.2 Mensagens Rápidas (Biblioteca)
- CRUD de mensagens: **texto, áudio, imagem, vídeo, documento**
- Campos de variável: `{{nome}}`, `{{grupo}}`, `{{link}}`, `{{empresa}}`
- Categorias/pastas de organização

### 4.3 Scripts Automáticos
- Sequência de passos: cada passo = mensagem + delay + **aguardar resposta** ou **ação** (ex: "se responder X, ir para passo Y")
- Editor visual simples (lista ordenada de passos)
- Modo teste (enviar para 1 contato)

### 4.4 Disparo em Massa
- Selecionar: instância + script + público (grupos ou contatos)
- **Intervalo dinâmico** entre mensagens (min/max segundos — randomizador)
- Limite diário por número + pausa noturna configurável
- Agendamento (data/hora)
- Progresso em tempo real + relatório (enviadas, entregues, respondidas, falhas)
- **Modo grupos**: disparo para membros de grupos (com extração de participantes)
- **Disparo seletivo por resposta anterior**: filtro "só enviar para quem NÃO
  respondeu" ou "somente leads na etapa X" — evita reenviar para quem já
  converteu (filtro por histórico de conversas)
- **Importar/exportar campanhas entre instâncias**: copiar scripts, mensagens
  e campanhas de uma instância para outra ("crie 1 vez, use em várias máquinas")
- **Backup/restauração**: exportar/importar toda a configuração (mensagens,
  scripts, gatilhos, etapas, grupos) em JSON
- **Anti-duplicação por lead**: não reenviar a mesma oferta/campanha para um
  lead que já recebeu nos últimos N dias (configurável; padrão 30)
- **Painel em tempo real**: contador ao vivo de envios/respostas (WebSocket/SSE)
- **⚙️ Ação pré-disparo em grupos: "Remover Admin"** (auto-demote do bot) —
  ao disparar em grupos de terceiros (ex: grupos de concorrentes, estratégia do
  vídeo 3), o número do bot pode ter sido promovido a admin sem intenção.
  Antes de disparar, o sistema oferece **remover o próprio admin** do grupo
  (via `POST /group/updateParticipant` com `action=demote`), para:
  1. Não chamar atenção (bot admin em grupo alheio é suspeito → risco de remoção/ban)
  2. Evitar mensagens com permissões de admin (ex: menção a todos sem querer)
  3. Padronizar o perfil de "membro comum" em todos os grupos-alvo
  - **Modo automático**: checkbox "remover admin antes do disparo" por campanha
  - **Modo manual**: botão por grupo na listagem (com confirmação)
  - Log da ação (quando removeu, grupo, instância)

### 4.5 Gatilhos Inteligentes (resposta automática)
- Regra: palavra-chave (ex: "quero", "grupo", "link", "preço") → resposta automática (msg da biblioteca)
- Por instância, opcional por grupo/contato
- Processado via **webhook da Evolution** (evento `messages.upsert`)
- Evita responder a mensagens do próprio bot (filtro de origem)
- **Gatilho avançado**: múltiplas palavras/condições por regra (OR/AND), ações
  múltiplas (responder + mudar etapa + notificar)
- **Gatilho por horário**: mensagem individual agendada para um lead em
  data/hora específica (ex: follow-up amanhã 14h) — diferente do disparo em
  massa agendado
- **Resposta com IA (chatbot contextual)** [v2]: modo "resposta inteligente"
  via LLM para perguntas abertas ("qual o preço?", "tem em outra cor?");
  se a IA não souber responder → alerta humano no painel + lead entra na fila
  (fallback humano)

### 4.6 Etapas / CRM
- Pipeline configurável: ex: `Novo → Contatado → Respondeu → Interessado → Vendido / Perdido`
- Mudança de etapa manual no painel OU automática por gatilho
- **Funil visual (kanban)**: arrastar leads entre etapas; visão de onde cada lead cai
- **Taxa de conversão por etapa** por campanha (relatório de funil)
- Histórico de conversas por contato
- Anotações/etiquetas por lead (multi-etiqueta)
- Exportação CSV

### 4.7 Anti-Banimento (Sistema AntiBlock)
- **Randomizador**: delay entre envios varia aleatoriamente (nunca fixo)
- **Delay dinâmico**: aumenta progressivamente se detectar falha/restrição
- **Limite diário** por número (ex: 30/50/100 — configurável)
- **Pausa noturna** (ex: 22h–7h sem envio)
- **Aquecimento de número**: rotina gradual (dia 1: 5 msgs, dia 2: 10...) antes de liberar disparos grandes
- Monitor de restrição: se a Evolution reportar `rate limit`/desconexão, pausa a fila automaticamente

### 4.8 Aquecedor de WhatsApp (RevProtect-like)
- Rotina automática de "vida normal" do número: enviar mensagens para contatos
  próprios, participar de grupos, variação de horários — simula humano
- Proteção passiva: atividade mínima diária para o número não parecer ocioso/robô
- (v1 simples: agendador com atividades aleatórias; v2: mais realista)

### 4.9 RevSaver-like (Status Saver)
- Baixar status (stories) de contatos — **despriorizado** (pode ficar fora da v1)

### 4.10 Contatos e Grupos
- Importação: CSV, WhatsApp (extração de membros de grupos)
- **Exportar contatos** (com etiquetas/etapas)
- Deduplicação por número

### 4.11 Painel (Dashboard)
- Visão geral: instâncias conectadas, envios hoje, taxa de resposta, leads por etapa
- Gráficos simples (envios/dia, conversão por campanha)
- Contadores ao vivo (WebSocket/SSE) durante disparos

### 4.12 Diferenciais do produto (vs Revzap)
- **D1 — Servidor próprio 24/7**: sem browser aberto; a Revzap é extensão Chrome
  que depende do WhatsApp Web + computador ligado
- **D2 — Multi-número nativo**: instâncias ilimitadas (Evolution API/Baileys);
  operar vários chips de uma tela
- **D3 — Anti-ban arquitetural**: controlador de ritmo centralizado (limite
  diário + pausa noturna + randomizador + auto-pausa em rate-limit) aplicado
  em TODOS os envios, com telemetria
- **D4 — Integração com ecossistema TechTeo**: pipeline Promo (links meli.la,
  cards, agendamento), Instagram (webhook), futuro EnergIA
- **D5 — Custo previsível**: infra própria (VPS + chips), sem assinatura por máquina
- **D6 — Dados próprios**: contatos/conversas no PostgreSQL (sem dependência de SaaS)
- **D7 — Relatório de funil**: taxa de conversão por etapa; onde o lead cai

### 4.13 Roadmap de inovação (extras — para ser único no mercado)
- **E1 — Funil "Grupo de Ofertas" pronto**: captar membros (vídeo 3) → nutrir
  com ofertas → converter em clique de afiliado, com dashboard de comissões
  por lead (integração links meli.la) [v2]
- **E2 — Aquecimento com persona de horário**: aprende o padrão real de uso do
  usuário e replica (mais natural que randomizar) [v2]
- **E3 — Respondedor IA + fallback humano**: LLM responde ~90%; se não souber,
  alerta humano no painel [v2]
- **E4 — API pública REST**: clientes integram (ex: disparar oferta do
  e-commerce via webhook) — vira produto B2B [v3]
- **E5 — Modo comunidade**: N grupos de ofertas coordenados com regras de
  rotação (evitar mesma oferta no mesmo dia) [v2]
- **E6 — Teste A/B de mensagens**: 2 variações → medir resposta → usar a
  vencedora no restante [v2]
- **E7 — Anti-duplicação por lead** (já em 4.4): mesma oferta não reenviada em
  N dias — essencial em grupos de ofertas
- **E8 — Painel em tempo real** (já em 4.4/4.11): WebSocket/SSE

---

## 5. Requisitos Não-Funcionais

| Área | Requisito |
|---|---|
| **Segurança** | Auth Django (django-allauth), 2FA opcional; API com token; rate limiting na API |
| **Confiabilidade** | Fila com retry (Celery + dead-letter); idempotência de envio (evitar duplicado em retry) |
| **Anti-ban** | Todos os envios passam pelo controlador de ritmo (nunca direto) |
| **Escalabilidade** | Multi-instância Evolution; worker horizontal |
| **Observabilidade** | Logs estruturados, métricas de envio, alerta de instância desconectada |
| **Multi-tenant** | (v2) separação por workspace/plano |

---

## 6. Modelo de Dados (entidades principais)

```text
Instance        (nome, evolution_token, status, limite_diario, ativo)
Campaign        (nome, instance_fk, script_fk, status, agendado_para, intervalo_min_s, intervalo_max_s)
CampaignContact (campaign_fk, contact_fk, status[pendente/enviada/respondida/erro], etapa)
Script          (nome, instância_fk?, passos JSON)
ScriptStep      (script_fk, ordem, tipo[msg|delay|aguardar_resposta|condicao], mensagem_fk?, delay_s?)
Message         (titulo, tipo[texto/audio/img/video/doc], conteudo, midia_url)
Contact         (numero, nome, grupo_fk?, etapa_fk?, tags)
Group           (nome, jid, instance_fk, membros_count)
Trigger         (instance_fk, palavra_chave, mensagem_fk, ativo)
Pipeline        (nome, etapas JSON)  →  LeadStage
Lead            (contact_fk, pipeline_fk, etapa_atual, historico JSON)
DeliveryLog     (campaign_contact_fk, status, timestamp, erro, message_id)
DailyLimit      (instance_fk, data, enviadas)
ScheduledMsg    (contact_fk, instance_fk, data_hora, mensagem_fk, status)  -- gatilho por horário (F6)
Backup          (tipo, arquivo_json, criado_em)  -- backup/restauração (F3)
ABTest          (campanha_fk, variante_a_fk, variante_b_fk, resultado)  -- Teste A/B (E6)
Commission      (lead_fk, campanha_fk, valor, link_afiliado, plataforma)  -- funil ofertas (E1)
```

---

## 7. Integração com a Evolution API (referência)

Base: `http://localhost:8080` · Header: `apikey: <AUTHENTICATION_API_KEY>`

| Ação | Endpoint |
|---|---|
| Criar instância | `POST /instance/create` `{instanceName}` |
| Conectar (QR) | `GET /instance/connect/{name}?number=` |
| Status | `GET /instance/connectionState/{name}` |
| Enviar texto | `POST /message/sendText/{name}` `{number, text}` |
| Enviar mídia | `POST /message/sendMedia/{name}` |
| Enviar áudio | `POST /message/sendWhatsAppAudio/{name}` |
| Mencionar | `POST /group/sendMention/{name}` (menciona todos) |
| Participantes do grupo | `GET /group/fetchAllParticipants/{name}/{groupJid}` |
| **Promover/Remover admin** | `POST /group/updateParticipant/{name}` `{groupJid, participants: [jid], action: promote\|demote}` (só admin do grupo; usamos `demote` p/ o auto-demote do bot) |
| Enviar para grupo | `POST /message/sendText/{name}` `{number: groupJid}` |
| Webhook eventos | `POST /webhook/set/{name}` `{webhook: {url, events: [...]}}` |
| Eventos relevantes | `messages.upsert`, `connection.update`, `contacts.upsert`, `messages.update` |

> ⚠️ **Nota importante:** a Evolution API é a camada de transporte. Todo o
> controle de ritmo/anti-ban fica na nossa aplicação (nunca confiar na API
> para limitar).

---

## 8. MVP (v1) — Escopo e Priorização

### Fase 1 (essencial — entrega rápida)
1. Instâncias (CRUD + QR + status) — usar a Evolution já instalada
2. Mensagens rápidas (texto + mídia) com variáveis
3. Scripts (mensagem + delay + aguardar resposta) — **o core do vídeo 3**
4. Disparo em massa com intervalo dinâmico + limite diário
5. Público: grupos importados (extração de participantes) + contatos CSV
6. Painel básico + relatório de envios
7. Gatilho simples: palavra-chave → resposta (via webhook)
8. **Remover Admin pré-disparo em grupos** (auto-demote)
9. **Anti-duplicação por lead** (não reenviar mesma campanha em N dias)

### Fase 2 (reforço)
10. Etapas/CRM com **funil kanban** + taxa de conversão por etapa
11. Aquecimento de número automático (+ persona de horário — E2)
12. Agendamento avançado + pausa noturna
13. Mencionar todos em grupos + **mencionar no privado por etiqueta** (F1)
14. **Disparo seletivo por resposta anterior** (só quem não respondeu — F5)
15. **Gatilho por horário individual** (follow-up agendado — F6)
16. **Importar/exportar campanhas entre instâncias** (F2) + backup/restauração (F3)
17. **Respondedor IA + fallback humano** (E3) + Teste A/B (E6)
18. **Funil "Grupo de Ofertas"** com comissões por lead (E1) + modo comunidade (E5)
19. Painel em tempo real (WebSocket/SSE — E8)

### Fase 3 (produto)
20. Multi-tenant, planos, billing, permissões de equipe
21. RevSaver (status saver)
22. **API pública REST** (E4)
23. Integração com afiliados (links automáticos meli.la, pipeline Promo)
24. App mobile (PWA)

---

## 9. Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| **Banimento de número** | Alta | Protocolo anti-ban rigoroso; chips dedicados; aquecimento; limites conservadores (padrão 30-50/dia) |
| **Evolution API instável/legada** | Média | Versão 2.3.7 já testada na VPS; fallback: Baileys direto (node) se necessário |
| **Webhook perdido (resposta do lead)** | Média | Fila de reconciliação periódica (poll de conversas) |
| **Duplicação de envio** | Média | Idempotência por `(campaign, contact)` + message_id da Evolution |
| **Scope creep** | Média | MVP enxuto; features Revs like RevSaver despriorizadas |
| **Custo de infra** | Baixa | VPS atual (1.8GB) + swap 4GB; Celery leve; monitorar RAM |

---

## 10. Métricas de Sucesso

- **v1 (uso interno):** disparar o fluxo do vídeo 3 sem banimento; ≥ 60% taxa de
  entrega; ≥ 20% taxa de resposta na msg 1; 100+ novos membros no grupo Promo
- **v2 (produto):** zero banimento nos últimos 30 dias; < R$ 5 custo por lead;
  churn < 5%/mês (se SaaS)

---

## 11. Próximos Passos (sugestão)

1. ✅ Validação da Evolution API (feita — instância `techteo` ativa)
2. Spikes: envio de texto via API + webhook de `messages.upsert` + extração de participantes de grupo
3. Scaffold Django + modelo de dados (seção 6)
4. Fase 1 itens 1-5
5. Teste real com 1 chip dedicado (aquecimento 14 dias antes de disparos grandes)

---

## Apêndice A — Glossário

- **Instância**: conexão da Evolution API com um número WhatsApp (chip dedicado)
- **Script**: sequência de passos de mensagens com delays e gatilhos
- **Disparo em massa**: envio do script para muitos contatos/grupos
- **Delay dinâmico**: intervalo aleatório entre envios (anti-padrão de robô)
- **Aquecimento**: rotina gradual de uso do número antes de disparos
- **Gatilho**: palavra-chave que dispara resposta automática

## Apêndice B — Referências

- Revzap oficial: https://revzap.com.br/ · https://revzap.com.br/oferta-especial/
- RevProtect: https://revprotect.revzap.com.br/
- Evolution API docs: https://doc.evolution-api.com/
- Vídeo 3 (origem da estratégia de 2 passos): [[Conhecimento/afiliados/yt-76RMGeEI2E-encher-grupo-whatsapp.md]]
