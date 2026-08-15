# Testes

Test runner próprio (`core.test_runner.SparzapTestRunner`, uma subclasse do
runner nativo), um `tests.py` por app. **218 testes** hoje.

```bash
.venv\Scripts\python manage.py test              # tudo
.venv\Scripts\python manage.py test antiblock    # um app

.venv\Scripts\python -m coverage run --source=. --omit=".venv/*,*/migrations/*,manage.py,*/tests.py" manage.py test
.venv\Scripts\python -m coverage report
```

Distribuição atual: `scripts` 39 · `contacts` 39 · `campaigns` 19 · `ai` 18 ·
`antiblock` 16 · `triggers` 13 · `core` 12 · `instances` 11 · `crm` 11 ·
`accounts` 11 · `webhooks` 9 · `reports` 8 · `api` 8 · `library` 4.

## Regras

### A suíte não depende do Celery da máquina

`core/test_runner.py` força `task_always_eager` em toda a suíte. Sem isso,
rodar os testes numa máquina com broker de verdade (`CELERY_TASK_ALWAYS_EAGER=False`
no `.env`, necessário para testar o ritmo real de uma campanha) enfileira as
tasks em vez de executá-las, e ~10 testes quebram: o webhook não processa o
evento, a campanha não dispara, o script não avança.

Mexer só no `settings` não basta — o app do Celery já leu a config no import,
então o runner também escreve em `celery_app.conf`.

### Nunca chame a Evolution API de verdade

Todo teste que envolva envio ou consulta mocka o cliente no ponto de uso:

```python
@patch('instances.evolution.EvolutionClient.send_text')
def test_dispatch_sucesso(self, mock_send):
    mock_send.return_value = {'key': {'id': 'ABC'}}
    ...
```

Vale para `send_text`, `connect`, `connection_state`, `fetch_all_groups` etc.

### Nem a IA — e cuidado com o que o mock esconde

Nenhum teste chama provedor de IA. Mocke o SDK na fronteira
(`anthropic.Anthropic`, `openai.OpenAI`, `google.genai.Client`), não o
`ai.services.classificar`.

Mockar `classificar` direto testa cada camada contra a sua própria versão
imaginada da outra. Foi assim que uma inversão passou: o
`PROMPT_TEMPLATE` embutia uma direção fixa ("concordar conta como SIM") que
contradizia descrições de direção oposta e invertia TODA a classificação —
e nenhum teste olhava o conteúdo do prompt. Hoje `ai.tests.PromptTemplateTests`
falha se o template voltar a presumir direção, e
`scripts.tests.ResolveCondicaoIAEndToEndTests` exercita a pilha inteira
mockando só o SDK.

Quando precisar mockar `classificar` (nos testes do motor), use
`autospec=True`: sem isso o mock aceita qualquer assinatura e uma troca na
ordem dos argumentos passa despercebida.

### Um teste que não pode falhar não é um teste

O primeiro `ResolveCondicaoIAEndToEndTests` apontava o desvio da condição
para o mesmo passo do fluxo normal — todos os caminhos possíveis (IA disse
sim, disse não, ou falhou) terminavam no mesmo lugar, e a única asserção
nunca falharia. Ao montar um teste de roteamento, garanta que os alvos dos
dois ramos sejam distintos e confirme que o mock foi realmente chamado.

### Custo em queries também é comportamento

`campaigns.tests.BuildAudienceEmLoteTests` mede **número de queries**, não
tempo: `build_audience` gravava um `get_or_create` por contato, e um grupo
real de 778 membros custava 3.117 queries — o gunicorn abortava a request
no timeout de 30s, enquanto o `runserver`, sem timeout, só ficava lento e
escondia o problema. Tempo varia por máquina; round-trips, não.

### Não dependa da hora em que o teste roda

`antiblock.can_send` bloqueia envio fora da janela de operação da instância,
cujo padrão é 08:00–21:00. Um teste que crie uma `Instance` com o default e
faça um envio **passa de dia e falha de madrugada**.

Quando o teste não for sobre a janela, abra-a explicitamente:

```python
self.instance = Instance.objects.create(
    ...,
    # janela cobrindo o dia inteiro: este teste nao e' sobre janela,
    # nao pode depender do horario real em que roda
    janela_inicio=datetime.time(0, 0),
    janela_fim=datetime.time(23, 59),
)
```

`core.factories.make_instance` já faz isso por padrão.

Pelo mesmo motivo, para simular bloqueio de forma determinística prefira
`limite_diario=0` (ou um `DailyLimit` estourado) em vez de manipular a
janela.

### Use as factories

`core/factories.py` tem fixtures reutilizáveis com defaults sensatos:

```python
from core.factories import make_user, make_instance, make_contact, make_message, make_script, make_campaign

owner = make_user()
instance = make_instance(owner=owner)      # já vem conectada, limite 50, janela 00:00–23:59
```

Testes escritos antes das factories criam objetos direto em `setUp()` e não
foram migrados. Código novo deve usar as factories.

### Teste pela porta de entrada real

Testes de view usam `django.test.Client` e batem na URL de verdade,
verificando status e conteúdo:

```python
r = self.client.get(f'/instancias/{instance.pk}/conectar/')
self.assertEqual(r.status_code, 200)
self.assertIn('src="data:image/png;base64,ABC123=="', r.content.decode())
```

`self.client.force_login(user)` autentica sem precisar da senha.

### Todo bug corrigido ganha um teste

Os testes de regressão do projeto seguem esse padrão — o nome descreve o
comportamento correto, não o bug:

```python
def test_qrcode_nao_duplica_prefixo_quando_evolution_ja_manda_data_uri(self):
def test_logout_via_get_nao_e_permitido(self):
```

Cubra as duas variantes quando a correção lida com formatos diferentes de
resposta externa (a Evolution muda payload entre versões).

## Convenções

- Nome do teste em português, descrevendo o comportamento esperado.
- Um `setUp()` por classe de teste, montando o cenário mínimo.
- Classes agrupadas por assunto (`CanSendTests`, `DispatchTests`,
  `WarmupTests`), não uma classe gigante por app.
- Antes de abrir PR: `manage.py test` verde **e** `flake8` com 0 issues.
