# Documentação do Sparzap

Índice da documentação técnica. O **produto** (requisitos, user stories,
roadmap de sprints) fica no [PRD.md](../PRD.md) na raiz do projeto; aqui
está só o que um dev precisa para trabalhar no código.

## Para quem vai usar o sistema

| Documento | Para quê |
|---|---|
| [manual-do-usuario.md](manual-do-usuario.md) | Manual do usuário final, ilustrado — do cadastro à primeira campanha |

## Comece por aqui

| Documento | Para quê |
|---|---|
| [ambiente.md](ambiente.md) | Subir o projeto na sua máquina e entender cada variável do `.env` |
| [arquitetura.md](arquitetura.md) | Como o projeto está dividido em apps e como um envio percorre o sistema |
| [padroes-de-codigo.md](padroes-de-codigo.md) | Convenções obrigatórias: camadas, nomes, imports, lint |

## Referência

| Documento | Conteúdo |
|---|---|
| [modelos.md](modelos.md) | Todos os models por app, com os relacionamentos e status |
| [rotas.md](rotas.md) | Mapa de todas as URLs do painel e dos webhooks |
| [tarefas-assincronas.md](tarefas-assincronas.md) | Celery, tasks periódicas e o modo eager de desenvolvimento |
| [frontend.md](frontend.md) | Templates, design tokens, componentes e template tags |
| [testes.md](testes.md) | Como rodar, como escrever e o que já é coberto |
| [api.md](api.md) | API REST pública (endpoints, autenticação por token) |
| [evolution.md](evolution.md) | Contrato da integração com a Evolution API (WhatsApp) |

## Operação

| Documento | Conteúdo |
|---|---|
| [DEPLOY.md](DEPLOY.md) | Deploy em VPS com Docker Compose |
| [RUNBOOK.md](RUNBOOK.md) | O que fazer quando algo quebra em produção |
