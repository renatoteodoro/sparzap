from django.contrib import admin

from .models import Backup


@admin.register(Backup)
class BackupAdmin(admin.ModelAdmin):
    list_display = ['owner', 'tipo', 'secoes', 'created_at']
    list_filter = ['tipo']
    readonly_fields = ['owner', 'tipo', 'secoes', 'conteudo', 'created_at']
