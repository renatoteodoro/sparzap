from django.contrib import admin

from .models import Script, ScriptRun, ScriptStep


class ScriptStepInline(admin.TabularInline):
    model = ScriptStep
    extra = 0
    fk_name = 'script'


@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    list_display = ['nome', 'owner']
    inlines = [ScriptStepInline]


@admin.register(ScriptRun)
class ScriptRunAdmin(admin.ModelAdmin):
    list_display = ['script', 'contact', 'status', 'origem', 'passo_atual', 'created_at']
    list_filter = ['status', 'origem']
    readonly_fields = ['erro']
