from django.contrib import admin

from .models import BlockEvent, DailyLimit, RateSettings, WarmupActivity, WarmupPlan


@admin.register(DailyLimit)
class DailyLimitAdmin(admin.ModelAdmin):
    list_display = ['instance', 'data', 'enviadas']
    list_filter = ['data']


@admin.register(RateSettings)
class RateSettingsAdmin(admin.ModelAdmin):
    list_display = ['instance', 'intervalo_min_s', 'intervalo_max_s', 'fator_escalonamento', 'falhas_consecutivas']


@admin.register(BlockEvent)
class BlockEventAdmin(admin.ModelAdmin):
    list_display = ['instance', 'motivo', 'pausou_instancia', 'created_at']
    list_filter = ['motivo', 'pausou_instancia']


class WarmupActivityInline(admin.TabularInline):
    model = WarmupActivity
    extra = 0
    readonly_fields = ['dia', 'limite_do_dia', 'created_at']
    can_delete = False


@admin.register(WarmupPlan)
class WarmupPlanAdmin(admin.ModelAdmin):
    list_display = ['instance', 'dia_atual', 'dias_total', 'status']
    list_filter = ['status']
    inlines = [WarmupActivityInline]
