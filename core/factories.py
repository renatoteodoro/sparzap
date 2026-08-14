"""
Fixtures/factories reutilizáveis para os testes (Sprint 17, 17.1.2).

Usadas pelos testes novos (`webhooks`, `instances`); os testes escritos nas
sprints anteriores criam seus próprios objetos em `setUp()` e não foram
retroativamente migrados para cá — ver PRD.md Sprint 17.
"""


def make_user(email='user@teste.com', nome='Usuário Teste', **kwargs):
    from accounts.models import User

    return User.objects.create_user(email=email, password='senha-teste-123', nome=nome, **kwargs)


def make_instance(owner=None, nome='Instância Teste', evolution_instance_name=None, **kwargs):
    import datetime

    from instances.models import Instance

    owner = owner or make_user()
    evolution_instance_name = evolution_instance_name or nome.lower().replace(' ', '-')
    kwargs.setdefault('status', Instance.STATUS_CONECTADO)
    kwargs.setdefault('limite_diario', 50)
    # janela cobrindo o dia inteiro por padrao: testes nao devem depender do
    # horario real em que rodam (ver antiblock.can_send / PRD Sprint 7);
    # quem quiser testar a janela em si passa janela_inicio/janela_fim explicitos.
    kwargs.setdefault('janela_inicio', datetime.time(0, 0))
    kwargs.setdefault('janela_fim', datetime.time(23, 59))
    return Instance.objects.create(owner=owner, nome=nome, evolution_instance_name=evolution_instance_name, **kwargs)


def make_contact(owner=None, numero_e164='+5511900000001', nome='Contato Teste', **kwargs):
    from contacts.models import Contact

    owner = owner or make_user()
    return Contact.objects.create(owner=owner, numero_e164=numero_e164, nome=nome, **kwargs)


def make_message(owner=None, titulo='Mensagem Teste', conteudo='Oi {{nome}}', **kwargs):
    from library.models import Message

    owner = owner or make_user()
    kwargs.setdefault('tipo', Message.TIPO_TEXTO)
    return Message.objects.create(owner=owner, titulo=titulo, conteudo=conteudo, **kwargs)


def make_script(owner=None, nome='Script Teste', **kwargs):
    from scripts.models import Script

    owner = owner or make_user()
    return Script.objects.create(owner=owner, nome=nome, **kwargs)


def make_campaign(owner=None, instance=None, script=None, nome='Campanha Teste', **kwargs):
    from campaigns.models import Campaign

    owner = owner or make_user()
    instance = instance or make_instance(owner=owner)
    script = script or make_script(owner=owner)
    return Campaign.objects.create(owner=owner, instance=instance, script=script, nome=nome, **kwargs)


def make_ai_config(owner=None, nome='Config IA Teste', modelo='claude-opus-5', api_key='chave-teste-123', **kwargs):
    from ai.models import AIConfig

    owner = owner or make_user()
    kwargs.setdefault('provider', AIConfig.PROVIDER_ANTHROPIC)
    return AIConfig.objects.create(owner=owner, nome=nome, modelo=modelo, api_key=api_key, **kwargs)
