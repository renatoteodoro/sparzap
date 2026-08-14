from django.contrib import admin

from .models import AdminActionLog, Contact, ContactList, ContactTag, Group, GroupMember, Tag


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['numero_e164', 'nome', 'owner', 'opt_out', 'ultimo_contato']
    list_filter = ['opt_out']
    search_fields = ['numero_e164', 'nome']


admin.site.register(Tag)
admin.site.register(ContactTag)
admin.site.register(ContactList)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['nome', 'instance', 'membros_count', 'bot_e_admin']
    list_filter = ['bot_e_admin', 'instance']
    search_fields = ['nome', 'jid']


admin.site.register(GroupMember)


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    list_display = ['group', 'instance', 'modo', 'resultado', 'created_at']
    list_filter = ['modo', 'resultado']
