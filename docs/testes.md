# Testes

Test runner nativo do Django, um `tests.py` por app. **128 testes** hoje,
cobertura de ~65%.

```bash
.venv\Scripts\python manage.py test              # tudo
.venv\Scripts\python manage.py test antiblock    # um app

.venv\Scripts\python -m coverage run --source=. --omit=".venv/*,*/migrations/*,manage.py,*/tests.py" manage.py test
.venv\Scripts\python -m coverage report
```

Distribuição atual: `contacts` 18 · `antiblock` 15 · `campaigns` 12 ·
`accounts` 11 · `crm` 11 · `triggers` 10 · `webhooks` 9 · `api` 8 ·
`instances` 8 · `reports` 8 · `core` 7 · `scripts` 7 · `library` 4.

## Regras

### Nunca chame a Evolution API de verdade

Todo teste que envolva envio ou consulta mocka o cliente no ponto de uso:

```python
@patch('instances.evolution.EvolutionClient.send_text')
def test_dispatch_sucesso(self, mock_send):
    mock_send.return_value = {'key': {'id': 'ABC'}}
    ...
```

Vale para `send_text`, `connect`, `connection_state`, `fetch_all_groups` etc.

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
