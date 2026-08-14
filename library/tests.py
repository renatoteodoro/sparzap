from django.test import TestCase

from .models import Message
from .services import render_message, unknown_variables


class RenderMessageTests(TestCase):
    def test_substitui_variaveis_conhecidas(self):
        msg = Message(titulo='t', conteudo='Oi {{nome}}, veja o grupo {{grupo}}: {{link}}')
        texto = render_message(msg, {'nome': 'Ana', 'grupo': 'Ofertas', 'link': 'http://x'}, usar_variante=False)
        self.assertEqual(texto, 'Oi Ana, veja o grupo Ofertas: http://x')

    def test_variavel_ausente_vira_vazio(self):
        msg = Message(titulo='t', conteudo='Oi {{nome}}!')
        self.assertEqual(render_message(msg, {}, usar_variante=False), 'Oi !')

    def test_unknown_variables_detecta_variavel_nao_suportada(self):
        self.assertEqual(unknown_variables('Oi {{nome}}, seu {{cpf}}'), ['cpf'])

    def test_unknown_variables_vazio_quando_tudo_suportado(self):
        self.assertEqual(unknown_variables('Oi {{nome}}, grupo {{grupo}}'), [])
