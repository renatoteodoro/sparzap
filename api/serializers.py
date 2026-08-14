from rest_framework import serializers

from campaigns.models import Campaign
from contacts.models import Contact
from crm.models import Lead
from instances.models import Instance


class InstanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instance
        fields = ['id', 'nome', 'status', 'limite_diario', 'ativo', 'numero', 'created_at']
        read_only_fields = fields


class CampaignSerializer(serializers.ModelSerializer):
    instance_nome = serializers.CharField(source='instance.nome', read_only=True)
    script_nome = serializers.CharField(source='script.nome', read_only=True)

    class Meta:
        model = Campaign
        fields = [
            'id',
            'nome',
            'instance',
            'instance_nome',
            'script',
            'script_nome',
            'status',
            'agendado_para',
            'filtro_publico',
            'antiduplicacao_dias',
            'remover_admin_antes',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'instance_nome', 'script_nome', 'created_at']


class CampaignReportSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    pendente = serializers.IntegerField()
    enviada = serializers.IntegerField()
    respondida = serializers.IntegerField()
    falha = serializers.IntegerField()


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ['id', 'numero_e164', 'nome', 'opt_out', 'ultimo_contato', 'created_at']
        read_only_fields = ['id', 'ultimo_contato', 'created_at']


class LeadSerializer(serializers.ModelSerializer):
    contato_numero = serializers.CharField(source='contact.numero_e164', read_only=True)
    contato_nome = serializers.CharField(source='contact.nome', read_only=True)
    etapa = serializers.CharField(source='stage.nome', read_only=True)

    class Meta:
        model = Lead
        fields = ['id', 'contato_numero', 'contato_nome', 'etapa', 'origem', 'entrou_na_etapa_em']
        read_only_fields = fields


class ScheduleMessageSerializer(serializers.Serializer):
    numero = serializers.CharField()
    instance_id = serializers.IntegerField()
    message_id = serializers.IntegerField()
    data_hora = serializers.DateTimeField()
