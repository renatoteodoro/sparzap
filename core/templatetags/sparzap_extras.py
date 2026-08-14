from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def sidebar_link(context, url, icon, label):
    """Item da sidebar com destaque em --green quando a rota atual bate com `url`."""
    request = context.get('request')
    active = bool(request and request.path == url)

    classes = 'flex items-center gap-3 px-5 py-2.5 text-sm font-sans transition-colors'
    if active:
        classes += ' text-green bg-white/5 border-r-2 border-green font-medium'
    else:
        classes += ' text-white/70 hover:text-white hover:bg-white/5'

    return format_html(
        '<a href="{}" class="{}"><span class="w-5 text-center">{}</span><span>{}</span></a>',
        url,
        classes,
        mark_safe(icon),
        label,
    )


# Cores de badge por status — ver PRD.md secao 9.5
_BADGE_TOKENS = {
    'green': 'text-green border-green/40 bg-green/10',
    'warning': 'text-warning border-warning/40 bg-warning/10',
    'danger': 'text-danger border-danger/40 bg-danger/10',
    'blue': 'text-blue border-blue/40 bg-blue/10',
    'gray': 'text-cool-gray border-silver bg-silver/10',
}

STATUS_BADGE_MAP = {
    # instâncias
    'conectado': 'green',
    'aguardando_qr': 'warning',
    'desconectado': 'gray',
    'banido': 'danger',
    # campanhas / genérico
    'enviada': 'green',
    'entregue': 'green',
    'vendido': 'green',
    'pausada': 'warning',
    'contatado': 'warning',
    'aquecendo': 'warning',
    'falha': 'danger',
    'perdido': 'danger',
    'rascunho': 'gray',
    'pendente': 'gray',
    'novo': 'gray',
    'respondeu': 'blue',
    'interessado': 'blue',
}


@register.simple_tag
def status_badge(status, label=None):
    token = _BADGE_TOKENS.get(STATUS_BADGE_MAP.get(status, 'gray'), _BADGE_TOKENS['gray'])
    texto = label or status
    return format_html(
        '<span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium border {}">{}</span>',
        token,
        texto,
    )
