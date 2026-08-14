from django.contrib import admin

from .models import Instance, InstanceEvent


class InstanceEventInline(admin.TabularInline):
    model = InstanceEvent
    extra = 0
    readonly_fields = ['status_anterior', 'status_novo', 'detalhe', 'created_at']
    can_delete = False


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
    list_display = ['nome', 'owner', 'status', 'limite_diario', 'ativo', 'ultimo_status_em']
    list_filter = ['status', 'ativo']
    search_fields = ['nome', 'evolution_instance_name', 'numero']
    inlines = [InstanceEventInline]


@admin.register(InstanceEvent)
class InstanceEventAdmin(admin.ModelAdmin):
    list_display = ['instance', 'status_anterior', 'status_novo', 'created_at']
    list_filter = ['status_novo']
