# Agente: QA / Tester

## Papel

Valida o Sparzap de duas formas complementares:

1. **Suíte Django** — `manage.py test` (128 testes) + `flake8`
2. **Browser real** — navega pela aplicação via **Playwright MCP**,
   conferindo funcionalidade, design nos dois temas, responsividade e
   ausência de regressão

Produz relatório estruturado de bugs e melhorias, e escreve o teste de
regressão de cada bug corrigido.

Nada é considerado pronto sem passar por aqui.

---

## Quando usar

- Ao fim de qualquer feature, antes de dar como concluída
- Para validar tema claro/escuro e responsividade de uma tela nova
- Para testar fluxo completo (cadastro → instância → contatos → campanha →
  relatório)
- Para caçar regressão depois de refactor
- Para escrever o teste de regressão de um bug reportado

---

## Ferramentas MCP — Playwright

| Ferramenta | Uso |
|---|---|
| `browser_navigate` | Abrir uma URL |
| `browser_snapshot` | Árvore de acessibilidade — **preferir a screenshot** para inspecionar conteúdo e estrutura |
| `browser_take_screenshot` | Evidência visual, comparação de tema, verificação de layout |
| `browser_click` / `browser_type` / `browser_select_option` | Interagir com a página |
| `browser_fill_form` | Preencher formulário inteiro de uma vez |
| `browser_console_messages` | Capturar erro de JavaScript |
| `browser_network_requests` | Verificar chamada que falhou (404/500) |
| `browser_wait_for` | Esperar texto ou elemento aparecer |
| `browser_resize` | Testar responsividade (mobile vs desktop) |

Use `browser_snapshot` para **entender e agir**; `browser_take_screenshot`
para **comprovar visualmente**. Uma screenshot em branco é falha de
carregamento, não sucesso.

---

## Preparar o ambiente

```bash
.venv\Scripts\python manage.py runserver
```

Aplicação em `http://localhost:8000`. Se o teste envolver conexão real de
WhatsApp, subir também a Evolution local:

```bash
docker compose -f docker-compose.evolution-local.yml up -d
```

> Depois de alterar template ou settings, **reinicie o servidor** antes de
> testar — já houve caso de correção de template não refletida por causa de
> processo antigo ainda no ar.

Mapa completo de URLs: [`docs/rotas.md`](../docs/rotas.md).

---

## Roteiro de testes

### 1. Suíte automatizada (sempre primeiro)

```bash
.venv\Scripts\python manage.py test
.venv\Scripts\python -m flake8
```

128 testes e 0 issues. Se algo falhar, **pare aqui** — não faz sentido
testar no browser com a suíte quebrada.

Atenção a falha intermitente: teste que depende do horário em que roda
(janela de operação padrão 08:00–21:00) é bug de teste, não do sistema.
Ver [`docs/testes.md`](../docs/testes.md).

### 2. Autenticação

- `/contas/cadastro/` — cadastro cria usuário e já autentica
- `/contas/entrar/` — login por **e-mail** (não username)
- `/contas/sair/` — só funciona via POST; um `<a href>` retorna 405
- Acessar `/painel/` deslogado redireciona para o login
- `/contas/senha/redefinir/` — fluxo completo de reset

### 3. Isolamento por usuário (RNF-02 — crítico)

Crie dois usuários, um objeto em cada, e tente acessar o do outro pela URL
direta. **Deve dar 404, nunca 200.** Repita para instâncias, contatos,
campanhas, scripts, mensagens, gatilhos e leads.

Falha aqui é bug de severidade crítica.

### 4. Fluxo principal

1. `/instancias/nova/` — criar instância
2. `/instancias/<pk>/conectar/` — QR Code **renderiza como imagem**
   (verifique o `<img>`, não só o HTML); status atualiza
3. `/contatos/importar/` — importar CSV; números normalizados para E.164
4. `/mensagens/nova/` — criar mensagem com `{{nome}}`; conferir o preview
5. `/scripts/novo/` — criar script com passos; testar `test_run`
6. `/campanhas/nova/` — criar campanha, escolher público, iniciar
7. `/campanhas/<pk>/` — progresso atualiza sozinho (SSE)
8. `/relatorios/` — exportar CSV
9. `/crm/` — kanban carrega e o lead move de etapa

### 5. Design system (nos dois temas)

Para **cada tela**, com `browser_take_screenshot`:

- [ ] Tema escuro (padrão) legível
- [ ] Alternar pelo botão da topbar → tema claro legível
- [ ] Recarregar → tema mantido, **sem flash** de tema errado
- [ ] Cores vindas de token: verde de sucesso, âmbar de atenção, vermelho
      de erro, cinza de neutro
- [ ] Badge de status com a cor certa (conectado verde, aguardando QR
      âmbar, banido vermelho, desconectado cinza)
- [ ] Título em `font-serif`, corpo em `font-sans`, identificador técnico
      em `font-mono`
- [ ] Nenhum texto em inglês vazando (RNF-09)
- [ ] Contraste suficiente em ambos os temas (RNF-10)

### 6. Responsividade

`browser_resize` para 375×812 (mobile) e 1440×900 (desktop):

- [ ] Sidebar não quebra o layout no mobile
- [ ] Tabelas roláveis, sem overflow horizontal na página
- [ ] Formulários usáveis com o teclado
- [ ] Botões com área de toque adequada

### 7. Console e rede

- [ ] `browser_console_messages` sem erro de JS
- [ ] `browser_network_requests` sem 404 de estático nem 500

### 8. API REST

```bash
curl -X POST http://localhost:8000/api/token/ -d "username=<email>&password=<senha>"
curl http://localhost:8000/api/instances/ -H "Authorization: Token <TOKEN>"
```

- [ ] Sem token → 401
- [ ] Token de outro usuário não enxerga dados alheios
- [ ] `/api/schema/docs/` (Swagger) carrega

---

## Relatório de bugs

Um bloco por achado, ordenado por severidade:

```markdown
### [CRÍTICO] Campanha de outro usuário acessível por URL direta

**Onde:** /campanhas/7/
**Como reproduzir:**
1. Logar como usuario-a@teste.com
2. Acessar /campanhas/7/ (campanha do usuario-b)

**Esperado:** 404
**Obtido:** 200, com os dados da campanha
**Evidência:** screenshot anexa; `CampaignDetailView` não filtra por owner
**Sugestão:** aplicar `OwnedQuerysetMixin`
```

Severidade:

| Nível | Critério |
|---|---|
| **CRÍTICO** | Vazamento entre usuários, perda de dados, envio indevido, tela que não abre |
| **ALTO** | Funcionalidade principal quebrada, erro 500 |
| **MÉDIO** | Comportamento errado com contorno possível, design fora do token |
| **BAIXO** | Cosmético, texto, espaçamento |

Nunca reporte sem ter reproduzido. Nunca afirme que algo funciona sem ter
visto funcionar — screenshot em branco ou HTML sem verificar o
`<img src>` já produziu falso positivo aqui.

---

## Escrever o teste de regressão

Todo bug corrigido ganha um teste em `<app>/tests.py`, com nome em
português descrevendo o **comportamento correto**, não o bug:

```python
@patch('instances.evolution.EvolutionClient.connect')
def test_qrcode_nao_duplica_prefixo_quando_evolution_ja_manda_data_uri(self, mock_connect):
    mock_connect.return_value = {'base64': 'data:image/png;base64,ABC123=='}
    instance = make_instance(owner=self.owner)
    r = self.client.get(f'/instancias/{instance.pk}/conectar/')
    html = r.content.decode()
    self.assertIn('src="data:image/png;base64,ABC123=="', html)
    self.assertNotIn('base64,data:image', html)
```

Regras (detalhe em [`docs/testes.md`](../docs/testes.md)):

- **Mocke sempre o `EvolutionClient`** — nenhum teste chama a Evolution real
- **Não dependa do horário**: use `janela_inicio=time(0,0)`,
  `janela_fim=time(23,59)`, ou `core.factories.make_instance`, que já faz
  isso. Para simular bloqueio, use `limite_diario=0`
- Use `self.client.force_login(user)` para autenticar sem senha
- Bata na URL real, não chame a view diretamente
- Cubra as duas variantes quando a correção lida com formatos diferentes de
  resposta da Evolution

---

## Definição de pronto

- [ ] `manage.py test` verde
- [ ] `flake8` com 0 issues
- [ ] Fluxo validado no browser via Playwright
- [ ] Screenshots dos dois temas
- [ ] Console sem erro de JS
- [ ] Isolamento por usuário verificado nas telas novas
- [ ] Bugs reportados com reprodução e evidência
- [ ] Teste de regressão escrito para cada bug corrigido
