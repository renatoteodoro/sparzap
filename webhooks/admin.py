from django.contrib import admin

from .models import WebhookEvent


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ['evento', 'instance', 'processado', 'created_at']
    list_filter = ['evento', 'processado', 'instance']
    search_fields = ['message_id']
    readonly_fields = ['instance', 'evento', 'message_id', 'payload', 'created_at']
