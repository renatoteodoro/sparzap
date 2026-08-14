from django.contrib import admin

from .models import ConversationMessage, Lead, LeadNote, Pipeline, Stage


class StageInline(admin.TabularInline):
    model = Stage
    extra = 0


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ['nome', 'owner']
    inlines = [StageInline]


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['contact', 'pipeline', 'stage', 'origem', 'entrou_na_etapa_em']
    list_filter = ['stage', 'pipeline']


admin.site.register(LeadNote)
admin.site.register(ConversationMessage)
