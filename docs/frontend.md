# Frontend

Django Template Language + TailwindCSS (Play CDN), sem build step e sem
framework JavaScript. Toda a UI é renderizada no servidor.

## Hierarquia de templates

```
base.html                    fontes, Tailwind, tokens, tema, <body>
├── base_app.html            sidebar + topbar + área de conteúdo (painel logado)
│   └── <app>/<pagina>.html  estende base_app, preenche os blocks
└── public/landing.html      página pública, estende base.html direto
```

Blocks disponíveis:

| Block | Onde | Para quê |
|---|---|---|
| `title` | `base.html` | Título da aba |
| `extra_head` / `extra_body` | `base.html` | CSS/JS específico da página |
| `body` | `base.html` | Corpo inteiro (usado por `base_app.html` e pela landing) |
| `page_title` | `base_app.html` | Título na topbar |
| `topbar_extra` | `base_app.html` | Botões de ação à direita da topbar |
| `app_content` | `base_app.html` | Conteúdo da página |

Templates ficam em `templates/<app>/`, na raiz do projeto — não em
`<app>/templates/`.

## Design tokens

Definidos em `static/css/tokens.css` como variáveis CSS e expostos ao
Tailwind por `static/js/tailwind-config.js`. **Use sempre a classe
utilitária, nunca o hexadecimal.**

| Classe Tailwind | Token | Uso |
|---|---|---|
| `bg-surface` / `text-ink` | `--white` / `--black` | Fundo e texto principais — **trocam de valor entre os temas** |
| `text-green` `bg-green` | `--green` `#00ed64` | Sucesso, status conectado, destaque |
| `dark-green` | `--dark-green` `#00684a` | Ações primárias |
| `blue` / `hover-blue` | `--blue` `#006cfa` | Links e informação |
| `forest` / `teal` / `teal-gray` | fundos escuros | Sidebar e superfícies escuras |
| `cool-gray` | texto secundário | |
| `silver` | bordas | |
| `warning` / `danger` | `#e5a000` / `#e53e3e` | Extensões do Sparzap (não vêm da fonte original) |

> Os nomes `--white` e `--black` são herdados da fonte do design system e
> **não devem ser lidos ao pé da letra**: representam fundo e texto, e no
> tema escuro `--white` é `#001e2b`.

Tipografia: `font-serif` (DM Serif Display, títulos), `font-sans` (Inter,
padrão), `font-mono` (Source Code Pro, identificadores técnicos).

Raios: `rounded-input` (4px), `rounded-link` (8px), `rounded-card` (16px),
`rounded-panel` (24px), `rounded-hero` (48px).

Sombras: `shadow-subtle`, `shadow-standard`, `shadow-forest`.

## Tema claro/escuro

`darkMode: 'class'`. O tema fica em `localStorage['sparzap-theme']` (padrão
`dark`) e é aplicado por um script inline no `<head>` **antes do primeiro
paint**, para não piscar. O botão `[data-theme-toggle]` na topbar alterna,
via `static/js/theme-toggle.js`.

Como os tokens já mudam de valor entre `:root.light` e `:root.dark`, na
maioria dos casos basta usar `bg-surface`/`text-ink` e nada mais é preciso.

## Template tags

Em `core/templatetags/sparzap_extras.py` (`{% load sparzap_extras %}`):

**`{% sidebar_link url icon label %}`** — item da sidebar, destacado em
verde quando `request.path` bate com a URL.

**`{% status_badge status label %}`** — badge colorida a partir do status.
O mapeamento está em `STATUS_BADGE_MAP`; status desconhecido cai em cinza.
Ao criar um status novo que apareça na UI, adicione-o lá.

## Componentes

| Arquivo | O que é |
|---|---|
| `components/sidebar.html` | Navegação lateral do painel |
| `components/navbar_public.html` | Topo da página pública |
| `components/footer.html` | Rodapé público |
| `components/messages.html` | Toasts do `django.contrib.messages`, com cor e ícone por tag |
| `components/coming_soon.html` | Placeholder de módulo ainda não implementado |

## Formulários

Não escreva classes CSS no template nem no widget. Chame
`apply_input_classes(self)` no `__init__` do form — as classes vêm de
`core/forms.py` (`INPUT_CLASSES`, `TEXTAREA_CLASSES`, `CHECKBOX_CLASSES`).

## Tempo real

O progresso de campanha usa **Server-Sent Events**: a rota
`campaigns:progress_stream` devolve um `text/event-stream` gerado por
`campaigns/sse.py`, com a contagem por status a cada 2 segundos. O stream
encerra sozinho quando a campanha sai de `em_andamento` (ou após ~1h).
Não há WebSocket nem Django Channels no projeto.

## Estáticos

Servidos pelo WhiteNoise. Em `DEBUG=True` usa
`CompressedStaticFilesStorage`; em produção,
`CompressedManifestStaticFilesStorage`, que **exige `collectstatic`** — por
isso a escolha é condicional no `settings.py`, e o `Dockerfile` roda
`collectstatic` no build.
