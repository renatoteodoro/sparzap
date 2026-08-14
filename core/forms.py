"""Classes Tailwind compartilhadas pelos widgets de formulário — design system MongoDB-inspired (PRD seção 9.3)."""

INPUT_CLASSES = (
    'w-full bg-surface text-ink border border-silver rounded-input px-3 py-2.5 '
    'text-sm font-sans font-light outline-none transition-colors '
    'focus:border-blue focus:ring-2 focus:ring-blue/20'
)

TEXTAREA_CLASSES = INPUT_CLASSES + ' min-h-[100px] resize-y'

SELECT_CLASSES = INPUT_CLASSES

CHECKBOX_CLASSES = 'rounded border-silver text-dark-green focus:ring-blue/20'


def apply_input_classes(form, overrides=None):
    """Aplica INPUT_CLASSES a todos os campos de um form; overrides={'nome_campo': classes}."""
    overrides = overrides or {}
    for name, field in form.fields.items():
        widget = field.widget
        css = overrides.get(name)
        if css:
            widget.attrs['class'] = css
        elif widget.__class__.__name__ in ('CheckboxInput',):
            widget.attrs['class'] = CHECKBOX_CLASSES
        elif widget.__class__.__name__ in ('Textarea',):
            widget.attrs['class'] = TEXTAREA_CLASSES
        else:
            widget.attrs['class'] = INPUT_CLASSES
    return form
