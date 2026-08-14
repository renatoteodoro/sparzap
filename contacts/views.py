from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from instances.models import Instance

from . import services
from .forms import ContactForm, GroupMessageForm, ImportCsvForm
from .models import Contact, Group


class OwnedQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class ContactListView(OwnedQuerysetMixin, ListView):
    model = Contact
    template_name = 'contacts/list.html'
    context_object_name = 'contacts'
    paginate_by = 50

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('tags')
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(numero_e164__icontains=q) | queryset.filter(nome__icontains=q)
        if self.request.GET.get('opt_out') == '1':
            queryset = queryset.filter(opt_out=True)
        return queryset


class ContactCreateView(LoginRequiredMixin, CreateView):
    model = Contact
    form_class = ContactForm
    template_name = 'contacts/form.html'
    success_url = reverse_lazy('contacts:list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, 'Contato criado.')
        return super().form_valid(form)


class ContactUpdateView(OwnedQuerysetMixin, UpdateView):
    model = Contact
    form_class = ContactForm
    template_name = 'contacts/form.html'
    success_url = reverse_lazy('contacts:list')

    def form_valid(self, form):
        messages.success(self.request, 'Contato atualizado.')
        return super().form_valid(form)


class ContactDeleteView(OwnedQuerysetMixin, DeleteView):
    model = Contact
    template_name = 'contacts/confirm_delete.html'
    success_url = reverse_lazy('contacts:list')


class ContactImportView(LoginRequiredMixin, View):
    template_name = 'contacts/import.html'

    def get(self, request):
        from django.shortcuts import render

        return render(request, self.template_name, {'form': ImportCsvForm()})

    def post(self, request):
        from django.shortcuts import render

        form = ImportCsvForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        resultado = services.import_csv(request.user, form.cleaned_data['arquivo'])
        messages.success(
            request,
            f"Importação concluída: {resultado['importados']} novos, "
            f"{resultado['duplicados']} já existentes, {resultado['invalidos']} inválidos.",
        )
        return redirect('contacts:list')


class ContactExportView(LoginRequiredMixin, View):
    def get(self, request):
        csv_content = services.export_csv(request.user)
        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="contatos.csv"'
        return response


class ContactBulkOptOutView(LoginRequiredMixin, View):
    def post(self, request):
        ids = request.POST.getlist('contact_ids')
        updated = Contact.objects.filter(owner=request.user, id__in=ids).update(opt_out=True)
        messages.success(request, f'{updated} contato(s) marcado(s) como opt-out.')
        return redirect('contacts:list')


class ContactDedupeView(LoginRequiredMixin, View):
    def post(self, request):
        removidos = services.dedupe_contacts(request.user)
        messages.success(request, f'{removidos} contato(s) duplicado(s) unificado(s).')
        return redirect('contacts:list')


# --- Grupos ------------------------------------------------------------


class GroupListView(LoginRequiredMixin, ListView):
    model = Group
    template_name = 'contacts/groups.html'
    context_object_name = 'groups'

    def get_queryset(self):
        return Group.objects.filter(instance__owner=self.request.user).select_related('instance')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['instances'] = Instance.objects.filter(owner=self.request.user)
        return context


class GroupSyncView(LoginRequiredMixin, View):
    def post(self, request, instance_pk):
        instance = get_object_or_404(Instance, pk=instance_pk, owner=request.user)
        grupos = services.sync_groups(instance)
        messages.success(request, f'{len(grupos)} grupo(s) sincronizado(s) de "{instance.nome}".')
        return redirect('contacts:groups')


class GroupSendMessageView(LoginRequiredMixin, View):
    """Envia mensagem (com ou sem mencao a todos) para o proprio grupo — RF-26/9.2.4-9.2.5."""

    def post(self, request, pk):
        from antiblock.services import AntiBlockBlocked, dispatch

        group = get_object_or_404(Group, pk=pk, instance__owner=request.user)
        form = GroupMessageForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Informe uma mensagem válida.')
            return redirect('contacts:groups')

        tipo = 'mention' if form.cleaned_data['mencionar_todos'] else 'texto'
        try:
            dispatch(group.instance, group.jid, form.cleaned_data['texto'], tipo=tipo)
            messages.success(request, f'Mensagem enviada para o grupo "{group.nome}".')
        except AntiBlockBlocked as exc:
            messages.error(request, f'Bloqueado pelo AntiBlock: {exc}')
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f'Falha ao enviar: {exc}')
        return redirect('contacts:groups')


class GroupExtractParticipantsView(LoginRequiredMixin, View):
    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk, instance__owner=request.user)
        contatos = services.extract_participants(group)
        messages.success(request, f'{len(contatos)} participante(s) extraído(s) de "{group.nome}".')
        return redirect('contacts:groups')


class GroupDemoteSelfView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from .models import AdminActionLog

        group = get_object_or_404(Group, pk=pk, instance__owner=request.user)
        resultado = services.demote_self(group, modo=AdminActionLog.MODO_MANUAL)
        rotulos = {
            AdminActionLog.RESULTADO_SUCESSO: 'Admin removido com sucesso.',
            AdminActionLog.RESULTADO_NAO_ERA_ADMIN: 'O bot já não era admin deste grupo.',
            AdminActionLog.RESULTADO_FALHA: 'Falha ao remover o admin — confira o log.',
        }
        if resultado == AdminActionLog.RESULTADO_FALHA:
            messages.error(request, rotulos[resultado])
        else:
            messages.success(request, rotulos[resultado])
        return redirect('contacts:groups')
