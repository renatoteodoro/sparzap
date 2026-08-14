"""
Backup/restauração de configuração ("crie uma vez, use em várias") — Sprint 15.

Exporta mensagens, scripts, gatilhos, pipelines e (definições de) campanhas
de um owner para um JSON versionado, e reimporta remapeando tudo para uma
instância de destino escolhida pelo usuário. Dados específicos de execução
(CampaignContact materializado, ScriptRun, DeliveryLog) NUNCA são
exportados — só a configuração reutilizável.
"""

from django.utils import timezone

SCHEMA_VERSION = 1
SECOES_DISPONIVEIS = ['mensagens', 'scripts', 'gatilhos', 'pipelines', 'campanhas']


def _serialize_mensagens(owner):
    from library.models import Message

    dados = []
    for msg in Message.objects.filter(owner=owner).select_related('folder').prefetch_related('variants'):
        dados.append(
            {
                'pasta': msg.folder.nome if msg.folder else None,
                'titulo': msg.titulo,
                'tipo': msg.tipo,
                'conteudo': msg.conteudo,
                'variantes': [v.conteudo for v in msg.variants.all()],
            }
        )
    return dados


def _serialize_scripts(owner):
    from scripts.models import Script

    dados = []
    for script in Script.objects.filter(owner=owner).prefetch_related('steps'):
        passos = []
        for step in script.steps.order_by('ordem'):
            passos.append(
                {
                    'ordem': step.ordem,
                    'tipo': step.tipo,
                    'mensagem_titulo': step.message.titulo if step.message else None,
                    'delay_s': step.delay_s,
                    'timeout_h': step.timeout_h,
                    'condicao_contem': step.condicao_contem,
                    'proximo_passo_ordem': step.proximo_passo.ordem if step.proximo_passo else None,
                    'etapa_destino': step.etapa_destino,
                }
            )
        dados.append({'nome': script.nome, 'descricao': script.descricao, 'passos': passos})
    return dados


def _serialize_gatilhos(owner):
    from triggers.models import Trigger

    dados = []
    for trigger in Trigger.objects.filter(owner=owner):
        dados.append(
            {
                'nome': trigger.nome,
                'palavras_chave': trigger.palavras_chave,
                'modo': trigger.modo,
                'resposta_titulo': trigger.resposta.titulo if trigger.resposta else None,
                'etiqueta_nome': trigger.etiqueta_nome,
                'etapa_destino': trigger.etapa_destino,
                'followup_mensagem_titulo': trigger.followup_mensagem.titulo if trigger.followup_mensagem else None,
                'followup_apos_horas': trigger.followup_apos_horas,
                'prioridade': trigger.prioridade,
                'limite_repeticao_minutos': trigger.limite_repeticao_minutos,
                'ativo': trigger.ativo,
            }
        )
    return dados


def _serialize_pipelines(owner):
    from crm.models import Pipeline

    dados = []
    for pipeline in Pipeline.objects.filter(owner=owner).prefetch_related('stages'):
        dados.append(
            {
                'nome': pipeline.nome,
                'etapas': [
                    {'nome': s.nome, 'ordem': s.ordem, 'cor': s.cor, 'e_final': s.e_final}
                    for s in pipeline.stages.order_by('ordem')
                ],
            }
        )
    return dados


def _serialize_campanhas(owner):
    from campaigns.models import Campaign

    dados = []
    for campaign in Campaign.objects.filter(owner=owner):
        dados.append(
            {
                'nome': campaign.nome,
                'script_nome': campaign.script.nome,
                'filtro_publico': campaign.filtro_publico,
                'antiduplicacao_dias': campaign.antiduplicacao_dias,
                'remover_admin_antes': campaign.remover_admin_antes,
            }
        )
    return dados


_SERIALIZERS = {
    'mensagens': _serialize_mensagens,
    'scripts': _serialize_scripts,
    'gatilhos': _serialize_gatilhos,
    'pipelines': _serialize_pipelines,
    'campanhas': _serialize_campanhas,
}


def export_config(owner, secoes=None):
    secoes = secoes or SECOES_DISPONIVEIS
    dados = {
        'schema_version': SCHEMA_VERSION,
        'gerado_em': timezone.now().isoformat(),
    }
    for secao in secoes:
        if secao in _SERIALIZERS:
            dados[secao] = _SERIALIZERS[secao](owner)
    return dados


# --- Importação --------------------------------------------------------


def validate_config(dados):
    if not isinstance(dados, dict) or 'schema_version' not in dados:
        return False, 'Arquivo não é um backup Sparzap válido (falta schema_version).'
    if dados['schema_version'] > SCHEMA_VERSION:
        return (
            False,
            f'Backup de uma versão mais nova ({dados["schema_version"]}) que este Sparzap suporta ({SCHEMA_VERSION}).',
        )
    return True, ''


def import_config(owner, target_instance, dados, conflito='ignorar'):
    """conflito: 'ignorar' | 'substituir' | 'renomear'."""
    relatorio = {'criados': 0, 'atualizados': 0, 'ignorados': 0}

    if 'mensagens' in dados:
        _import_mensagens(owner, dados['mensagens'], conflito, relatorio)
    if 'scripts' in dados:
        _import_scripts(owner, dados['scripts'], conflito, relatorio)
    if 'pipelines' in dados:
        _import_pipelines(owner, dados['pipelines'], conflito, relatorio)
    if 'gatilhos' in dados:
        _import_gatilhos(owner, target_instance, dados['gatilhos'], conflito, relatorio)
    if 'campanhas' in dados:
        _import_campanhas(owner, target_instance, dados['campanhas'], conflito, relatorio)

    return relatorio


def _import_mensagens(owner, itens, conflito, relatorio):
    from library.models import Message, MessageFolder, MessageVariant

    for item in itens:
        folder = None
        if item.get('pasta'):
            folder, _ = MessageFolder.objects.get_or_create(owner=owner, nome=item['pasta'])

        existente = Message.objects.filter(owner=owner, titulo=item['titulo']).first()
        if existente and conflito == 'ignorar':
            relatorio['ignorados'] += 1
            continue

        titulo = item['titulo']
        if existente and conflito == 'renomear':
            titulo = f"{item['titulo']} (importado)"
            existente = None

        if existente and conflito == 'substituir':
            msg = existente
            msg.conteudo = item['conteudo']
            msg.tipo = item['tipo']
            msg.folder = folder
            msg.save()
            msg.variants.all().delete()
            relatorio['atualizados'] += 1
        else:
            msg = Message.objects.create(
                owner=owner, folder=folder, titulo=titulo, tipo=item['tipo'], conteudo=item['conteudo']
            )
            relatorio['criados'] += 1

        for variante in item.get('variantes', []):
            MessageVariant.objects.create(message=msg, conteudo=variante)


def _import_scripts(owner, itens, conflito, relatorio):
    from library.models import Message
    from scripts.models import Script, ScriptStep

    for item in itens:
        existente = Script.objects.filter(owner=owner, nome=item['nome']).first()
        if existente and conflito == 'ignorar':
            relatorio['ignorados'] += 1
            continue

        nome = item['nome']
        if existente and conflito == 'renomear':
            nome = f"{item['nome']} (importado)"
            existente = None

        if existente and conflito == 'substituir':
            script = existente
            script.descricao = item['descricao']
            script.save()
            script.steps.all().delete()
            relatorio['atualizados'] += 1
        else:
            script = Script.objects.create(owner=owner, nome=nome, descricao=item.get('descricao', ''))
            relatorio['criados'] += 1

        passos_por_ordem = {}
        for passo in item['passos']:
            mensagem = (
                Message.objects.filter(owner=owner, titulo=passo['mensagem_titulo']).first()
                if passo.get('mensagem_titulo')
                else None
            )
            novo = ScriptStep.objects.create(
                script=script,
                ordem=passo['ordem'],
                tipo=passo['tipo'],
                message=mensagem,
                delay_s=passo.get('delay_s'),
                timeout_h=passo.get('timeout_h'),
                condicao_contem=passo.get('condicao_contem', ''),
                etapa_destino=passo.get('etapa_destino', ''),
            )
            passos_por_ordem[passo['ordem']] = novo

        for passo in item['passos']:
            if passo.get('proximo_passo_ordem') is not None:
                alvo = passos_por_ordem.get(passo['proximo_passo_ordem'])
                if alvo:
                    atual = passos_por_ordem[passo['ordem']]
                    atual.proximo_passo = alvo
                    atual.save(update_fields=['proximo_passo'])


def _import_pipelines(owner, itens, conflito, relatorio):
    from crm.models import Pipeline, Stage

    for item in itens:
        pipeline, criado = Pipeline.objects.get_or_create(owner=owner, nome=item['nome'])
        if not criado and conflito == 'ignorar':
            relatorio['ignorados'] += 1
            continue
        relatorio['criados' if criado else 'atualizados'] += 1
        for etapa in item['etapas']:
            Stage.objects.get_or_create(
                pipeline=pipeline,
                nome=etapa['nome'],
                defaults={'ordem': etapa['ordem'], 'cor': etapa['cor'], 'e_final': etapa['e_final']},
            )


def _import_gatilhos(owner, target_instance, itens, conflito, relatorio):
    from library.models import Message
    from triggers.models import Trigger

    for item in itens:
        existente = Trigger.objects.filter(owner=owner, nome=item['nome']).first()
        if existente and conflito == 'ignorar':
            relatorio['ignorados'] += 1
            continue

        nome = item['nome']
        if existente and conflito == 'renomear':
            nome = f"{item['nome']} (importado)"
            existente = None

        resposta = (
            Message.objects.filter(owner=owner, titulo=item.get('resposta_titulo')).first()
            if item.get('resposta_titulo')
            else None
        )
        followup_mensagem = (
            Message.objects.filter(owner=owner, titulo=item.get('followup_mensagem_titulo')).first()
            if item.get('followup_mensagem_titulo')
            else None
        )

        campos = {
            'instance': target_instance,
            'palavras_chave': item['palavras_chave'],
            'modo': item['modo'],
            'resposta': resposta,
            'etiqueta_nome': item.get('etiqueta_nome', ''),
            'etapa_destino': item.get('etapa_destino', ''),
            'followup_mensagem': followup_mensagem,
            'followup_apos_horas': item.get('followup_apos_horas'),
            'prioridade': item.get('prioridade', 100),
            'limite_repeticao_minutos': item.get('limite_repeticao_minutos', 60),
            'ativo': item.get('ativo', True),
        }

        if existente and conflito == 'substituir':
            for campo, valor in campos.items():
                setattr(existente, campo, valor)
            existente.save()
            relatorio['atualizados'] += 1
        else:
            Trigger.objects.create(owner=owner, nome=nome, **campos)
            relatorio['criados'] += 1


def _import_campanhas(owner, target_instance, itens, conflito, relatorio):
    from campaigns.models import Campaign
    from scripts.models import Script

    for item in itens:
        script = Script.objects.filter(owner=owner, nome=item['script_nome']).first()
        if script is None:
            relatorio['ignorados'] += 1
            continue

        existente = Campaign.objects.filter(owner=owner, nome=item['nome']).first()
        if existente and conflito == 'ignorar':
            relatorio['ignorados'] += 1
            continue

        nome = item['nome']
        if existente and conflito == 'renomear':
            nome = f"{item['nome']} (importado)"
            existente = None

        campos = {
            'instance': target_instance,
            'script': script,
            'filtro_publico': item['filtro_publico'],
            'antiduplicacao_dias': item['antiduplicacao_dias'],
            'remover_admin_antes': item['remover_admin_antes'],
        }
        if existente and conflito == 'substituir':
            for campo, valor in campos.items():
                setattr(existente, campo, valor)
            existente.save()
            relatorio['atualizados'] += 1
        else:
            Campaign.objects.create(owner=owner, nome=nome, **campos)
            relatorio['criados'] += 1
