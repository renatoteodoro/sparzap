# Padrões de código

Convenções que o projeto inteiro já segue. Ao adicionar código novo, siga
o que está aqui em vez de introduzir um estilo diferente.

## Idioma

- **Domínio em português**: nomes de campos (`limite_diario`, `janela_inicio`),
  constantes de status (`STATUS_CONECTADO`), funções de negócio
  (`build_audience` é exceção herdada; prefira `pode_receber_disparo`,
  `dispatch_due_scheduled_messages`), `verbose_name`, mensagens ao usuário,
  comentários e docstrings.
- **Framework em inglês**: nomes de classe Django (`InstanceListView`,
  `CampaignForm`), `related_name` quando é técnico, métodos que sobrescrevem
  o Django (`get_queryset`, `form_valid`).

Textos exibidos ao usuário são sempre em português (`LANGUAGE_CODE = 'pt-br'`).

## Regra de negócio fica em `services.py`

Views e tasks são casca fina. Uma view valida o form, chama um service e
devolve a resposta; uma task busca o objeto e chama um service.

```python
# views.py — certo
def post(self, request, pk):
    instance = get_object_or_404(self.get_queryset(), pk=pk)
    services.deactivate_instance(instance)
    messages.success(request, f'Instância "{instance.nome}" desativada.')
    return redirect('instances:list')
```

Services levantam exceções próprias do domínio (`AntiBlockBlocked`,
`EvolutionError`) e a view traduz para `messages.error`.

## Models

Todo model herda de `core.models.BaseModel`, que traz `created_at` e
`updated_at`:

```python
from core.models import BaseModel

class Instance(BaseModel):
    ...
```

Padrões dentro do model:

- **Status como constantes de classe** + `_CHOICES`, nunca strings soltas:
  ```python
  STATUS_CONECTADO = 'conectado'
  STATUS_CHOICES = [(STATUS_CONECTADO, 'Conectado'), ...]
  status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DESCONECTADO)
  ```
- **`verbose_name` em português** no campo e no `Meta`
  (`verbose_name = 'instância'`, `verbose_name_plural = 'instâncias'`).
- **`ordering` explícito** no `Meta` — os models já definem o padrão de
  ordenação esperado pelas listagens.
- **Multi-tenant por `owner`**: models de nível superior têm
  `owner = ForeignKey(settings.AUTH_USER_MODEL, ...)`. Models
  subordinados chegam ao dono pela FK do pai (ex.: `DailyLimit` →
  `instance.owner`).
- **`UniqueConstraint` nomeada** em vez de `unique_together` para
  restrições novas (`uniq_owner_numero`, `uniq_campaign_contact`).
- **`__str__` sempre definido**, retornando algo legível no Admin.

Ao alterar um campo, gere a migração (`makemigrations`) e confira o
resultado — um `default` errado já causou bug real aqui (`TimeField` com
default string em vez de `datetime.time`).

## Views

- Todas as views de painel exigem login. Use `LoginRequiredMixin`.
- Isolamento por usuário: cada app repete o mesmo mixin local

  ```python
  class OwnedQuerysetMixin(LoginRequiredMixin):
      def get_queryset(self):
          return self.model.objects.filter(owner=self.request.user)
  ```

  Views que não usam `get_queryset` (ações `View.post`) devem filtrar
  explicitamente: `get_object_or_404(Model.objects.filter(owner=request.user), pk=pk)`.
- **Ação que muda estado é `POST`**, nunca `GET` — inclusive logout
  (`LogoutView` do Django rejeita `GET` com 405).
- Class-Based Views para CRUD (`ListView`, `CreateView`, `UpdateView`,
  `DeleteView`, `DetailView`); `View` com `post()` para ações pontuais
  (pausar, retomar, sincronizar).
- Feedback ao usuário via `django.contrib.messages`.

## URLs

Cada app tem `app_name` e usa nomes curtos, referenciados como
`app:nome`:

```python
app_name = 'instances'
urlpatterns = [
    path('', views.InstanceListView.as_view(), name='list'),
    path('<int:pk>/conectar/', views.InstanceConnectView.as_view(), name='connect'),
]
```

Os segmentos da URL são em português (`/instancias/1/conectar/`), os nomes
de rota em inglês (`instances:connect`).

## Forms

`ModelForm` sempre que houver model por trás. As classes Tailwind vêm de
`core/forms.py` — não escreva classe CSS direto no widget:

```python
from core.forms import apply_input_classes

class InstanceForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        self.fields['nome'].widget.attrs['placeholder'] = 'Ex.: Vendas 01'
```

## Imports

Ordem definida em `setup.cfg` (isort, perfil black):
`stdlib → django → terceiros → apps do projeto → local`.

**Import tardio (dentro da função) é intencional** em dois casos, e ambos
aparecem bastante no código:

1. Quebrar ciclo entre apps (`campaigns` ↔ `scripts` ↔ `crm`).
2. Evitar carregar app pesado no import do módulo.

Sempre com um comentário curto explicando, como já é feito:

```python
from contacts import services as contacts_services  # import tardio: quebra de ciclo entre apps
```

## Tratamento de erro

Um `except Exception` amplo só é aceitável quando derrubar o fluxo seria
pior que engolir o erro — e sempre com `# noqa: BLE001` e um comentário
justificando:

```python
except Exception:  # noqa: BLE001 — alerta nunca pode derrubar o fluxo que o disparou
    logger.exception('falha ao enviar alerta para ALERT_WEBHOOK_URL')
```

Casos onde isso já é usado: processamento de webhook, execução de passo de
script, envio de alerta, log de CRM. Em qualquer outro lugar, capture a
exceção específica.

## Logging

Um logger só, `sparzap`, com mensagens em formato `chave=valor` para serem
filtráveis:

```python
logger = logging.getLogger('sparzap')
logger.info('dispatch_campaign campaign=%s agendados=%s', campaign_id, agendados)
```

Use `%s` (lazy), não f-string, nas chamadas de log. Em produção o formatter
vira JSON automaticamente (`DEBUG=False`).

## Lint e formatação

```bash
.venv\Scripts\python -m flake8      # precisa passar com 0 issues
.venv\Scripts\python -m black .
.venv\Scripts\python -m isort .
```

Linha de até 120 caracteres, aspas simples preservadas
(`skip-string-normalization`). Migrations e `.venv` ficam fora de tudo.
