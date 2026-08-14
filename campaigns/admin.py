from django.contrib import admin

from .models import Campaign, CampaignContact, DeliveryLog


class CampaignContactInline(admin.TabularInline):
    model = CampaignContact
    extra = 0
    readonly_fields = ['contact', 'status', 'enviado_em', 'respondido_em', 'erro']
    can_delete = False


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['nome', 'owner', 'instance', 'script', 'status', 'created_at']
    list_filter = ['status', 'instance']
    inlines = [CampaignContactInline]


@admin.register(CampaignContact)
class CampaignContactAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'contact', 'status', 'enviado_em']
    list_filter = ['status']


admin.site.register(DeliveryLog)
