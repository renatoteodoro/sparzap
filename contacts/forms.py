from django import forms

from core.forms import apply_input_classes

from .models import Contact, Tag


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['numero_e164', 'nome', 'opt_out']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        self.fields['numero_e164'].widget.attrs['placeholder'] = '+5511987654321'


class ImportCsvForm(forms.Form):
    arquivo = forms.FileField(label='Arquivo CSV')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)


class GroupMessageForm(forms.Form):
    texto = forms.CharField(label='Mensagem', widget=forms.Textarea)
    mencionar_todos = forms.BooleanField(label='Mencionar todos', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['nome', 'cor']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
