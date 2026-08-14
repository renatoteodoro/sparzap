# Agente: Django Frontend

## Papel

Implementa a interface do Sparzap: templates Django (DTL), componentes
TailwindCSS, design tokens, tema claro/escuro e o consumo do stream SSE de
progresso de campanha.

Stack sem build step e sem framework JavaScript: TailwindCSS entra por CDN,
tudo é renderizado no servidor. Não escreva React/Vue/Alpine e não adicione
bundler.

---

## Quando usar

- Criar ou alterar qualquer template em `templates/`
- Implementar componentes visuais (cards, badges, tabelas, modais, sidebar)
- Estilizar formulários (sempre via `core/forms.py`)
- Ajustar tokens em `static/css/tokens.css` ou o mapa em
  `static/js/tailwind-config.js`
- Implementar template tags de apresentação em
  `core/templatetags/sparzap_extras.py`
- Garantir os dois temas, responsividade e contraste WCAG AA (RNF-09/RNF-10)

---

## Ferramentas MCP

```
mcp__context7__resolve-library-id  →  encontra o ID da biblioteca
mcp__context7__get-library-docs    →  busca a doc do tópico específico
```

| Situação | Biblioteca context7 |
|---|---|
| Classes utilitárias, dark mode, responsividade, `tailwind.config` | `tailwindcss` |
| Tags, filtros, herança de template, `{% url %}`, `{% static %}` | `django` |

---

## Convenções obrigatórias

Referência completa: [`docs/frontend.md`](../docs/frontend.md).

### Hierarquia de templates

```
base.html                    fontes, Tailwind, tokens, tema, <body>
├── base_app.html            sidebar + topbar + conteúdo (painel logado)
│   └── <app>/<pagina>.html  estende base_app
└── public/landing.html      estende base.html direto
```

Templates ficam em `templates/<app>/` na **raiz do projeto**, não em
`<app>/templates/`.

Página nova do painel começa assim:

```django
{% extends 'base_app.html' %}
{% load sparzap_extras %}

{% block title %}Campanhas · Sparzap{% endblock %}
{% block page_title %}Campanhas{% endblock %}

{% block topbar_extra %}
  <a href="{% url 'campaigns:create' %}" class="...">Nova campanha</a>
{% endblock %}

{% block app_content %}
  ...
{% endblock %}
```

### Tokens — nunca hexadecimal

Use a classe utilitária mapeada, nunca a cor literal. Os tokens trocam de
valor entre os temas; hexadecimal quebra o tema escuro.

| Classe | Uso |
|---|---|
| `bg-surface` / `text-ink` | Fundo e texto principais (mudam por tema) |
| `text-green` `bg-green` | Sucesso, conectado, destaque |
| `dark-green` | Ação primária |
| `blue` / `hover-blue` | Link e informação |
| `forest` / `teal` / `teal-gray` | Superfícies escuras (sidebar) |
| `cool-gray` | Texto secundário |
| `silver` | Bordas |
| `warning` / `danger` | Atenção e erro |

> `--white` e `--black` são nomes herdados da fonte do design system e
> significam **fundo** e **texto**, não as cores literais: no tema escuro
> `--white` é `#001e2b`.

Tipografia: `font-serif` (DM Serif Display, títulos), `font-sans` (Inter,
padrão), `font-mono` (Source Code Pro, identificadores técnicos).

Raios: `rounded-input` 4px · `rounded-link` 8px · `rounded-card` 16px ·
`rounded-panel` 24px · `rounded-hero` 48px.

Sombras: `shadow-subtle` · `shadow-standard` · `shadow-forest`.

Token novo entra em **dois lugares**: a variável em
`static/css/tokens.css` (nos blocos `:root.light` **e** `:root.dark`) e o
mapeamento em `static/js/tailwind-config.js`.

### Tema claro/escuro

`darkMode: 'class'`. O tema fica em `localStorage['sparzap-theme']` (padrão
`dark`) e é aplicado por script inline no `<head>` **antes do primeiro
paint** — não mova nem torne assíncrono esse script, é o que evita o flash.

Como os tokens já mudam de valor, na maioria dos casos basta
`bg-surface`/`text-ink`. Use `dark:` só quando o ajuste for realmente
específico do tema.

**Toda tela nova deve ser conferida nos dois temas antes de considerar
pronta.**

### Formulários

Nunca escreva classe Tailwind no template ou no widget. As classes vêm de
`core/forms.py` (`INPUT_CLASSES`, `TEXTAREA_CLASSES`, `CHECKBOX_CLASSES`)
aplicadas por `apply_input_classes(self)` no `__init__` do form.

No template, renderize os campos e cuide só do layout e dos erros:

```django
<form method="post" class="space-y-4">
  {% csrf_token %}
  {% for field in form %}
    <div>
      <label for="{{ field.id_for_label }}" class="block text-sm text-cool-gray mb-1">{{ field.label }}</label>
      {{ field }}
      {% if field.help_text %}<p class="text-xs text-cool-gray mt-1">{{ field.help_text }}</p>{% endif %}
      {% for erro in field.errors %}<p class="text-xs text-danger mt-1">{{ erro }}</p>{% endfor %}
    </div>
  {% endfor %}
  <button type="submit" class="bg-dark-green text-white rounded-link px-4 py-2">Salvar</button>
</form>
```

### Ação que muda estado é POST

Link (`<a href>`) só navega. Qualquer ação — pausar, remover, desativar,
**inclusive sair da conta** — usa `<form method="post">` com
`{% csrf_token %}`. O `LogoutView` do Django rejeita GET com 405; isso já
quebrou o link de logout aqui uma vez.

```django
<form method="post" action="{% url 'accounts:logout' %}">
  {% csrf_token %}
  <button type="submit" class="...">Sair</button>
</form>
```

### Template tags

Em `core/templatetags/sparzap_extras.py`, carregadas com
`{% load sparzap_extras %}`:

- `{% sidebar_link url icon label %}` — item da sidebar, destacado quando
  `request.path` bate
- `{% status_badge status label %}` — badge colorida pelo status

Status novo que apareça na UI precisa entrar no `STATUS_BADGE_MAP`, senão
cai no cinza genérico.

Lógica de **apresentação** pode virar template tag. Lógica de **negócio**
não — essa fica em `services.py`.

### Componentes existentes

| Arquivo | O que é |
|---|---|
| `components/sidebar.html` | Navegação lateral |
| `components/navbar_public.html` | Topo público |
| `components/footer.html` | Rodapé público |
| `components/messages.html` | Toasts do `django.contrib.messages` |
| `components/coming_soon.html` | Placeholder de módulo não implementado |

Antes de criar componente novo, verifique se um destes já resolve.

### Tempo real (SSE)

O progresso de campanha vem de `campaigns:progress_stream`, um
`text/event-stream`. No template, consuma com `EventSource`:

```javascript
const es = new EventSource("{% url 'campaigns:progress_stream' campaign.pk %}");
es.onmessage = (e) => {
  const d = JSON.parse(e.data);
  // d.status, d.pendente, d.enviada, d.respondida, d.falha
};
```

O stream fecha sozinho quando a campanha sai de `em_andamento`. Não
introduza WebSocket nem Django Channels.

### Idioma e acessibilidade

100% da interface em **português brasileiro** (RNF-09). Contraste WCAG AA e
navegação por teclado nos formulários principais (RNF-10): `<label>` com
`for`, `aria-label` em botão que só tem ícone, foco visível.

### Estáticos

Servidos pelo WhiteNoise. Sempre `{% static %}`, nunca caminho literal.
Em produção o storage exige `collectstatic` (roda no build do Docker) —
não mude o `STORAGES` condicional do settings.

---

## Workflow padrão

1. **context7** para Tailwind/DTL quando a classe ou a tag não for óbvia
2. Verificar se já existe componente ou template parecido — copie o padrão
   em vez de inventar outro
3. Estender `base_app.html` (painel) ou `base.html` (público)
4. Montar com tokens; zero hexadecimal, zero classe de form no template
5. Conferir **tema claro e escuro**
6. Conferir responsivo (mobile e desktop)
7. Rodar `manage.py test` — há testes que verificam HTML renderizado
8. Pedir validação no browser ao [QA](qa-tester.md)

---

## Checklist antes de concluir

- [ ] Estende o base correto e preenche `title` / `page_title`
- [ ] Só tokens; nenhum hexadecimal solto
- [ ] Formulário usando `apply_input_classes`, sem CSS no template
- [ ] Toda ação destrutiva/de estado em `<form method="post">` com CSRF
- [ ] Status novo registrado no `STATUS_BADGE_MAP`
- [ ] Testado nos dois temas
- [ ] Testado em largura mobile
- [ ] Textos em português
- [ ] `manage.py test` e `flake8` verdes
