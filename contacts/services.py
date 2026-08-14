import csv
import io
import logging

from django.db import transaction
from django.utils import timezone

from instances.evolution import EvolutionClient, EvolutionError

from .models import AdminActionLog, Contact, Group, GroupMember
from .utils import normalize_br_number

logger = logging.getLogger('sparzap')


# --- Webhook -------------------------------------------------------------


def upsert_contact_from_webhook(owner, numero_raw, nome=''):
    numero = normalize_br_number(numero_raw)
    if not numero:
        logger.debug('upsert_contact_from_webhook numero_invalido raw=%s', numero_raw)
        return None

    contact, created = Contact.objects.get_or_create(
        owner=owner,
        numero_e164=numero,
        defaults={'nome': nome},
    )
    updates = {'ultimo_contato': timezone.now()}
    if nome and not contact.nome:
        updates['nome'] = nome
    for field, value in updates.items():
        setattr(contact, field, value)
    contact.save(update_fields=list(updates.keys()) + ['updated_at'])
    return contact


# --- Deduplicação ----------------------------------------------------------


def dedupe_contacts(owner):
    """
    Unifica contatos duplicados do mesmo owner com o mesmo numero_e164
    normalizado (pode acontecer se o numero foi salvo antes da normalizacao,
    ou por corrida entre importacao e webhook). Mantem o mais antigo,
    remapeia tags/listas/grupos e apaga os demais.

    Faz 2 passadas: primeiro agrupa por numero normalizado sem gravar nada
    (evita colidir com a constraint unique_together ao tentar renomear um
    contato para um numero que outro contato ainda-nao-processado já tem);
    só depois de mesclar/apagar os duplicados é que renomeia o sobrevivente.
    """
    grupos = {}
    for contact in Contact.objects.filter(owner=owner).order_by('created_at'):
        numero = normalize_br_number(contact.numero_e164) or contact.numero_e164
        grupos.setdefault(numero, []).append(contact)

    removidos = 0
    for numero, contatos in grupos.items():
        principal, *duplicados = contatos
        for contact in duplicados:
            _mesclar_em(principal, contact)
            removidos += 1
        if principal.numero_e164 != numero:
            principal.numero_e164 = numero
            principal.save(update_fields=['numero_e164', 'updated_at'])

    return removidos


def _mesclar_em(principal, contact):
    with transaction.atomic():
        principal.tags.add(*contact.tags.all())
        principal.listas.add(*contact.listas.all())
        GroupMember.objects.filter(contact=contact).exclude(
            group__in=GroupMember.objects.filter(contact=principal).values('group'),
        ).update(contact=principal)
        if not principal.nome and contact.nome:
            principal.nome = contact.nome
            principal.save(update_fields=['nome', 'updated_at'])
        contact.delete()


# --- Importação / exportação CSV ------------------------------------------


def import_csv(owner, file_obj, mapping=None):
    """
    mapping: {'numero': <indice_coluna>, 'nome': <indice_coluna>} — se None,
    assume a primeira coluna como numero e a segunda (se existir) como nome.
    """
    mapping = mapping or {'numero': 0, 'nome': 1}
    text = file_obj.read()
    if isinstance(text, bytes):
        text = text.decode('utf-8-sig', errors='ignore')

    reader = csv.reader(io.StringIO(text))
    linhas = list(reader)
    if linhas and _parece_cabecalho(linhas[0]):
        linhas = linhas[1:]

    resultado = {'importados': 0, 'duplicados': 0, 'invalidos': 0}
    for linha in linhas:
        if not linha:
            continue
        numero_raw = linha[mapping['numero']] if len(linha) > mapping['numero'] else ''
        nome = linha[mapping['nome']] if mapping.get('nome') is not None and len(linha) > mapping['nome'] else ''

        numero = normalize_br_number(numero_raw)
        if not numero:
            resultado['invalidos'] += 1
            continue

        _, created = Contact.objects.get_or_create(
            owner=owner,
            numero_e164=numero,
            defaults={'nome': nome.strip()},
        )
        resultado['importados' if created else 'duplicados'] += 1

    return resultado


def _parece_cabecalho(linha):
    primeira_coluna = (linha[0] if linha else '').strip().lower()
    return primeira_coluna in ('numero', 'número', 'telefone', 'phone', 'whatsapp')


def export_csv(owner, filtros=None):
    filtros = filtros or {}
    queryset = Contact.objects.filter(owner=owner).prefetch_related('tags')
    if filtros.get('tag_id'):
        queryset = queryset.filter(tags__id=filtros['tag_id'])
    if filtros.get('lista_id'):
        queryset = queryset.filter(listas__id=filtros['lista_id'])

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['numero', 'nome', 'etiquetas', 'opt_out'])
    for contact in queryset.distinct():
        etiquetas = ','.join(tag.nome for tag in contact.tags.all())
        writer.writerow([contact.numero_e164, contact.nome, etiquetas, contact.opt_out])
    return buffer.getvalue()


# --- Grupos ----------------------------------------------------------------


def sync_groups(instance):
    client = EvolutionClient()
    try:
        data = client.fetch_all_groups(instance.evolution_instance_name)
    except EvolutionError as exc:
        logger.warning('sync_groups_erro instance=%s error=%s', instance.evolution_instance_name, exc)
        return []

    grupos_criados = []
    for item in data if isinstance(data, list) else data.get('groups', []):
        jid = item.get('id') or item.get('jid')
        if not jid:
            continue
        group, _ = Group.objects.update_or_create(
            instance=instance,
            jid=jid,
            defaults={
                'nome': item.get('subject') or item.get('name') or jid,
                'membros_count': item.get('size') or item.get('participants', 0) or 0,
            },
        )
        grupos_criados.append(group)
    return grupos_criados


def extract_participants(group):
    client = EvolutionClient()
    try:
        data = client.fetch_all_participants(group.instance.evolution_instance_name, group.jid)
    except EvolutionError as exc:
        logger.warning('extract_participants_erro group=%s error=%s', group.jid, exc)
        return []

    participantes = data if isinstance(data, list) else data.get('participants', [])
    numero_do_bot = normalize_br_number(group.instance.numero) if group.instance.numero else None
    bot_encontrado_admin = False
    contatos = []

    for participante in participantes:
        jid_participante = participante.get('id') or participante.get('jid', '')
        numero = normalize_br_number(jid_participante)

        # so sabemos identificar o proprio bot na lista de participantes
        # comparando com o numero conectado da instancia (Instance.numero,
        # preenchido a partir do connection.update); sem isso, nao ha campo
        # confiavel e documentado que marque "este participante sou eu".
        e_o_proprio_bot = bool(numero_do_bot and numero == numero_do_bot)
        if e_o_proprio_bot and participante.get('admin'):
            bot_encontrado_admin = True

        if not numero or e_o_proprio_bot:
            continue  # o bot nunca deve virar Contact/lead do proprio grupo

        contact, _ = Contact.objects.get_or_create(
            owner=group.instance.owner,
            numero_e164=numero,
            defaults={'nome': participante.get('name', '') or ''},
        )
        GroupMember.objects.get_or_create(
            group=group,
            contact=contact,
            defaults={'jid_participante': jid_participante},
        )
        contatos.append(contact)

    group.membros_count = len(contatos)
    if bot_encontrado_admin:
        group.bot_e_admin = True
    group.save(update_fields=['membros_count', 'bot_e_admin', 'updated_at'])

    return contatos


# --- Auto-demote (RF-48 / 6.6.1) -----------------------------------------


def demote_self(group, modo=AdminActionLog.MODO_MANUAL):
    """
    Remove o próprio admin do bot num grupo alheio antes do disparo (para não
    chamar atenção — ver PRD.md secao 6.6.1). Não faz nada se o bot não for
    admin do grupo (`Group.bot_e_admin`).
    """
    instance = group.instance

    if not group.bot_e_admin:
        AdminActionLog.objects.create(
            instance=instance,
            group=group,
            modo=modo,
            resultado=AdminActionLog.RESULTADO_NAO_ERA_ADMIN,
        )
        return AdminActionLog.RESULTADO_NAO_ERA_ADMIN

    numero_do_bot = normalize_br_number(instance.numero) if instance.numero else None
    if not numero_do_bot:
        AdminActionLog.objects.create(
            instance=instance,
            group=group,
            modo=modo,
            resultado=AdminActionLog.RESULTADO_FALHA,
            detalhe='Instance.numero não preenchido (aguardando connection.update)',
        )
        return AdminActionLog.RESULTADO_FALHA

    jid_do_bot = numero_do_bot.lstrip('+') + '@s.whatsapp.net'
    client = EvolutionClient()
    try:
        client.update_participant(
            instance.evolution_instance_name, group.jid, action='demote', participants=[jid_do_bot]
        )
    except EvolutionError as exc:
        logger.warning('demote_self_erro group=%s error=%s', group.jid, exc)
        AdminActionLog.objects.create(
            instance=instance,
            group=group,
            modo=modo,
            resultado=AdminActionLog.RESULTADO_FALHA,
            detalhe=str(exc)[:255],
        )
        return AdminActionLog.RESULTADO_FALHA

    group.bot_e_admin = False
    group.save(update_fields=['bot_e_admin', 'updated_at'])
    AdminActionLog.objects.create(instance=instance, group=group, modo=modo, resultado=AdminActionLog.RESULTADO_SUCESSO)
    return AdminActionLog.RESULTADO_SUCESSO


def demote_self_for_campaign(campaign):
    """Modo automático: roda o auto-demote em todos os grupos-alvo da campanha antes do disparo."""
    resultados = []
    for group in campaign.grupos.all():
        resultados.append(demote_self(group, modo=AdminActionLog.MODO_AUTOMATICO))
    return resultados
