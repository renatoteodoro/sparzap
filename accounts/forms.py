from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User

INPUT_CLASSES = (
    'w-full bg-surface text-ink border border-silver rounded-input px-3 py-2.5 '
    'text-sm font-sans font-light outline-none transition-colors '
    'focus:border-blue focus:ring-2 focus:ring-blue/20'
)


class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['nome', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs['class'] = INPUT_CLASSES
        self.fields['nome'].widget.attrs['placeholder'] = 'Seu nome'
        self.fields['email'].widget.attrs['placeholder'] = 'voce@empresa.com'
        self.fields['password1'].widget.attrs['placeholder'] = 'Crie uma senha'
        self.fields['password2'].widget.attrs['placeholder'] = 'Confirme a senha'


class EmailAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'E-mail'
        self.fields['username'].widget.attrs.update(
            {
                'class': INPUT_CLASSES,
                'placeholder': 'voce@empresa.com',
                'autofocus': True,
            }
        )
        self.fields['password'].widget.attrs.update(
            {
                'class': INPUT_CLASSES,
                'placeholder': 'Sua senha',
            }
        )
