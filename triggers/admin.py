from django.contrib import admin

from .models import ScheduledMsg, Trigger, TriggerLog


@admin.register(Trigger)
class TriggerAdmin(admin.ModelAdmin):
    list_display = ['nome', 'instance', 'palavras_chave', 'modo', 'ativo', 'prioridade']
    list_filter = ['ativo', 'instance']


@admin.register(TriggerLog)
class TriggerLogAdmin(admin.ModelAdmin):
    list_display = ['trigger', 'contact', 'acoes_executadas', 'created_at']


@admin.register(ScheduledMsg)
class ScheduledMsgAdmin(admin.ModelAdmin):
    list_display = ['contact', 'instance', 'data_hora', 'status', 'origem']
    list_filter = ['status', 'origem']
