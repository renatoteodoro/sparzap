from unittest.mock import patch

from django.test import TestCase

from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounts.models import User
from campaigns.models import Campaign
from instances.models import Instance
from library.models import Message
from scripts.models import Script


class ApiAuthTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='api@api.com', password='x')
        self.token = Token.objects.create(user=self.owner)
        self.client = APIClient()

    def test_sem_token_retorna_401(self):
        r = self.client.get('/api/instances/')
        self.assertEqual(r.status_code, 401)

    def test_com_token_valido_retorna_200(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        r = self.client.get('/api/instances/')
        self.assertEqual(r.status_code, 200)

    def test_isolamento_por_usuario_instancias(self):
        outro = User.objects.create_user(email='outro@api.com', password='x')
        Instance.objects.create(owner=outro, nome='DoOutro', evolution_instance_name='do-outro')
        Instance.objects.create(owner=self.owner, nome='Minha', evolution_instance_name='minha')

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        r = self.client.get('/api/instances/')
        nomes = [i['nome'] for i in r.json()['results']]
        self.assertEqual(nomes, ['Minha'])

    def test_isolamento_por_usuario_nao_acessa_campanha_de_outro(self):
        outro = User.objects.create_user(email='outro2@api.com', password='x')
        inst_outro = Instance.objects.create(owner=outro, nome='I', evolution_instance_name='i-outro')
        script_outro = Script.objects.create(owner=outro, nome='S')
        campanha_outro = Campaign.objects.create(
            owner=outro, nome='CampOutro', instance=inst_outro, script=script_outro
        )

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        r = self.client.get(f'/api/campaigns/{campanha_outro.pk}/')
        self.assertEqual(r.status_code, 404)


class ApiEndpointTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='ep@ep.com', password='x')
        self.token = Token.objects.create(user=self.owner)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.instance = Instance.objects.create(
            owner=self.owner,
            nome='I1',
            evolution_instance_name='i1',
            status=Instance.STATUS_CONECTADO,
            limite_diario=50,
        )
        self.script = Script.objects.create(owner=self.owner, nome='S1')
        self.message = Message.objects.create(owner=self.owner, titulo='M1', tipo='texto', conteudo='Oi')

    def test_criar_contato_normaliza_numero(self):
        r = self.client.post('/api/contacts/', {'numero_e164': '11988887777', 'nome': 'Fulano'})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['numero_e164'], '+5511988887777')

    def test_criar_e_iniciar_campanha(self):
        r = self.client.post('/api/campaigns/', {'nome': 'C1', 'instance': self.instance.id, 'script': self.script.id})
        self.assertEqual(r.status_code, 201)
        campaign_id = r.json()['id']

        with patch('instances.evolution.EvolutionClient.send_text') as mock_send:
            mock_send.return_value = {'key': {'id': 'X1'}}
            r = self.client.post(f'/api/campaigns/{campaign_id}/start/')
        self.assertEqual(r.status_code, 200)

        r = self.client.get(f'/api/campaigns/{campaign_id}/report/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('total', r.json())

    def test_agendar_mensagem(self):
        r = self.client.post(
            '/api/messages/schedule/',
            {
                'numero': '11977776666',
                'instance_id': self.instance.id,
                'message_id': self.message.id,
                'data_hora': '2027-01-01T10:00:00Z',
            },
        )
        self.assertEqual(r.status_code, 201)

    def test_listar_leads_vazio_nao_quebra(self):
        r = self.client.get('/api/leads/')
        self.assertEqual(r.status_code, 200)
