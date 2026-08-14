from django import forms

from core.forms import apply_input_classes

from .models import Message, MessageFolder
from .services import unknown_variables

MAX_MEDIA_SIZE_MB = 16
ALLOWED_EXTENSIONS = {
    Message.TIPO_IMAGEM: ['.jpg', '.jpeg', '.png', '.webp'],
    Message.TIPO_VIDEO: ['.mp4', '.mov'],
    Message.TIPO_AUDIO: ['.mp3', '.ogg', '.m4a', '.opus'],
    Message.TIPO_DOCUMENTO: ['.pdf', '.doc', '.docx', '.xls', '.xlsx'],
}


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['titulo', 'folder', 'tipo', 'conteudo', 'midia']

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        if owner is not None:
            self.fields['folder'].queryset = MessageFolder.objects.filter(owner=owner)
        self.fields['conteudo'].widget.attrs['placeholder'] = 'Ex.: Oi {{nome}}, tudo bem? Confira: {{link}}'

    def clean_conteudo(self):
        conteudo = self.cleaned_data['conteudo']
        desconhecidas = unknown_variables(conteudo)
        if desconhecidas:
            raise forms.ValidationError(
                f"Variáveis não suportadas: {', '.join('{{' + v + '}}' for v in desconhecidas)}. "
                f"Use apenas nome, grupo, link, empresa."
            )
        return conteudo

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        midia = cleaned_data.get('midia')

        if tipo != Message.TIPO_TEXTO and not midia:
            self.add_error('midia', 'Obrigatória para mensagens que não são de texto.')
            return cleaned_data

        if midia and tipo in ALLOWED_EXTENSIONS:
            import os

            ext = os.path.splitext(midia.name)[1].lower()
            if ext not in ALLOWED_EXTENSIONS[tipo]:
                self.add_error(
                    'midia',
                    f"Extensão '{ext}' não permitida para {tipo}. Use: {', '.join(ALLOWED_EXTENSIONS[tipo])}.",
                )
            if midia.size > MAX_MEDIA_SIZE_MB * 1024 * 1024:
                self.add_error('midia', f'Arquivo maior que {MAX_MEDIA_SIZE_MB}MB.')

        return cleaned_data


class MessageFolderForm(forms.ModelForm):
    class Meta:
        model = MessageFolder
        fields = ['nome']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
