from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from . import services
from .evolution import EvolutionError
from .forms import InstanceForm, TestMessageForm
from .models import Instance


class OwnedQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class InstanceListView(OwnedQuerysetMixin, ListView):
    model = Instance
    template_name = 'instances/list.html'
    context_object_name = 'instances'


class InstanceCreateView(LoginRequiredMixin, CreateView):
    model = Instance
    form_class = InstanceForm
    template_name = 'instances/form.html'

    def form_valid(self, form):
        try:
            self.object = services.provision_instance(
                owner=self.request.user,
                nome=form.cleaned_data['nome'],
                evolution_instance_name=form.cleaned_data['evolution_instance_name'],
                limite_diario=form.cleaned_data['limite_diario'],
            )
        except Exception as exc:  # noqa: BLE001 — reporta qualquer falha de provisionamento ao usuário
            form.add_error(None, f'Não foi possível criar a instância: {exc}')
            return self.form_invalid(form)
        messages.success(self.request, f'Instância "{self.object.nome}" criada. Conecte o QR Code para ativar.')
        return redirect('instances:connect', pk=self.object.pk)


class InstanceUpdateView(OwnedQuerysetMixin, UpdateView):
    model = Instance
    form_class = InstanceForm
    template_name = 'instances/form.html'
    success_url = reverse_lazy('instances:list')

    def form_valid(self, form):
        messages.success(self.request, 'Instância atualizada.')
        return super().form_valid(form)


class InstanceDeleteView(OwnedQuerysetMixin, DeleteView):
    model = Instance
    template_name = 'instances/confirm_delete.html'
    success_url = reverse_lazy('instances:list')

    def form_valid(self, form):
        messages.success(self.request, 'Instância removida.')
        return super().form_valid(form)


class InstanceConnectView(OwnedQuerysetMixin, DetailView):
    model = Instance
    template_name = 'instances/connect.html'
    context_object_name = 'instance'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            data = services.get_qrcode(self.object)
            base64_bruto = data.get('base64') or data.get('qrcode', {}).get('base64') or ''
            # a Evolution real (v2.3.7) já retorna a data URI completa
            # ("data:image/png;base64,...."), não só o payload — normaliza
            # aqui para o template sempre poder montar "data:image/png;base64,{{ }}"
            # sem duplicar o prefixo (senão o <img> fica com src inválido e
            # nunca renderiza, mesmo com o payload correto).
            if base64_bruto.startswith('data:'):
                base64_bruto = base64_bruto.split(',', 1)[-1]
            context['qrcode_base64'] = base64_bruto
            context['pairing_code'] = data.get('pairingCode')
        except EvolutionError as exc:
            context['evolution_error'] = str(exc)
        context['test_form'] = TestMessageForm()

        from django.utils import timezone

        from antiblock.models import DailyLimit

        limite = DailyLimit.objects.filter(instance=self.object, data=timezone.localdate()).first()
        context['enviadas_hoje'] = limite.enviadas if limite else 0
        context['percentual_hoje'] = (
            min(100, round(100 * context['enviadas_hoje'] / self.object.limite_diario))
            if self.object.limite_diario
            else 0
        )
        return context


class InstanceRefreshStatusView(OwnedQuerysetMixin, View):
    model = Instance

    def post(self, request, pk):
        instance = get_object_or_404(self.get_queryset(), pk=pk)
        try:
            services.refresh_status(instance)
            messages.success(request, f'Status atualizado: {instance.get_status_display()}')
        except EvolutionError as exc:
            messages.error(request, f'Não foi possível consultar o status: {exc}')
        return redirect('instances:connect', pk=pk)


class InstanceTestMessageView(OwnedQuerysetMixin, View):
    model = Instance

    def post(self, request, pk):
        instance = get_object_or_404(self.get_queryset(), pk=pk)
        form = TestMessageForm(request.POST)
        if form.is_valid():
            try:
                services.send_test_message(instance, form.cleaned_data['numero'])
                messages.success(request, 'Mensagem de teste enviada.')
            except EvolutionError as exc:
                messages.error(request, f'Falha ao enviar teste: {exc}')
        else:
            messages.error(request, 'Informe um número válido.')
        return redirect('instances:connect', pk=pk)


class InstanceDeactivateView(OwnedQuerysetMixin, View):
    model = Instance

    def post(self, request, pk):
        instance = get_object_or_404(self.get_queryset(), pk=pk)
        services.deactivate_instance(instance)
        messages.success(request, f'Instância "{instance.nome}" desativada.')
        return redirect('instances:list')
