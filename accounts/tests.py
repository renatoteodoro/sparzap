from django.test import Client, TestCase

from .models import User


class UserManagerTests(TestCase):
    def test_create_user_normaliza_email_e_define_senha(self):
        user = User.objects.create_user(email='Fulano@Exemplo.com', password='senha123', nome='Fulano')
        self.assertEqual(user.email, 'Fulano@exemplo.com')
        self.assertTrue(user.check_password('senha123'))
        self.assertFalse(user.is_staff)

    def test_create_user_sem_email_levanta_erro(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email='', password='x')

    def test_create_superuser_define_flags(self):
        admin = User.objects.create_superuser(email='admin@x.com', password='x')
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_username_field_e_email(self):
        self.assertEqual(User.USERNAME_FIELD, 'email')


class AuthFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='login@teste.com', password='senha-forte-123', nome='Login Teste')

    def test_login_por_email_funciona(self):
        ok = self.client.login(username='login@teste.com', password='senha-forte-123')
        self.assertTrue(ok)

    def test_signup_cria_usuario_e_loga(self):
        r = self.client.post(
            '/contas/cadastro/',
            {
                'nome': 'Novo Usuario',
                'email': 'novo@teste.com',
                'password1': 'senha-bem-forte-456',
                'password2': 'senha-bem-forte-456',
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(email='novo@teste.com').exists())

    def test_dashboard_exige_login(self):
        r = self.client.get('/painel/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/contas/entrar/', r.url)

    def test_dashboard_acessivel_logado(self):
        self.client.login(username='login@teste.com', password='senha-forte-123')
        r = self.client.get('/painel/')
        self.assertEqual(r.status_code, 200)

    def test_logout_via_post_encerra_a_sessao(self):
        # LogoutView (Django >= 4.1) so aceita POST -- o link do sidebar precisa
        # ser um <form method="post">, nunca um <a href> (GET retorna 405).
        self.client.login(username='login@teste.com', password='senha-forte-123')
        r = self.client.post('/contas/sair/')
        self.assertEqual(r.status_code, 302)

        r2 = self.client.get('/painel/')
        self.assertEqual(r2.status_code, 302)
        self.assertIn('/contas/entrar/', r2.url)

    def test_logout_via_get_nao_e_permitido(self):
        self.client.login(username='login@teste.com', password='senha-forte-123')
        r = self.client.get('/contas/sair/')
        self.assertEqual(r.status_code, 405)

    def test_sidebar_usa_form_post_para_logout_nao_link(self):
        self.client.login(username='login@teste.com', password='senha-forte-123')
        r = self.client.get('/painel/')
        html = r.content.decode()
        self.assertIn('action="/contas/sair/"', html)
        self.assertNotIn('href="/contas/sair/"', html)
