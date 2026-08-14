from django.contrib import admin

from .models import Message, MessageFolder, MessageVariant


class MessageVariantInline(admin.TabularInline):
    model = MessageVariant
    extra = 1


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'tipo', 'owner', 'folder']
    list_filter = ['tipo', 'folder']
    search_fields = ['titulo', 'conteudo']
    inlines = [MessageVariantInline]


admin.site.register(MessageFolder)
