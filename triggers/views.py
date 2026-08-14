from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from contacts.models import Contact

from . import services
from .forms import ScheduledMsgForm, TriggerForm, TriggerTestForm
from .models import ScheduledMsg, Trigger, TriggerLog


class OwnedQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class TriggerListView(OwnedQuerysetMixin, ListView):
    model = Trigger
    template_name = 'triggers/list.html'
    context_object_name = 'triggers'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['test_form'] = TriggerTestForm()
        return context


class TriggerCreateView(LoginRequiredMixin, CreateView):
    model = Trigger
    form_class = TriggerForm
    template_name = 'triggers/form.html'
    success_url = reverse_lazy('triggers:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['owner'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, 'Gatilho criado.')
        return super().form_valid(form)


class TriggerUpdateView(OwnedQuerysetMixin, UpdateView):
    model = Trigger
    form_class = TriggerForm
    template_name = 'triggers/form.html'
    success_url = reverse_lazy('triggers:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['owner'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Gatilho atualizado.')
        return super().form_valid(form)


class TriggerDeleteView(OwnedQuerysetMixin, DeleteView):
    model = Trigger
    template_name = 'triggers/confirm_delete.html'
    success_url = reverse_lazy('triggers:list')


class TriggerTestView(LoginRequiredMixin, View):
    """Simula 'esta mensagem recebida' sem persistir TriggerLog — usado para depurar gatilhos."""

    def post(self, request):
        form = TriggerTestForm(request.POST)
        if not form.is_valid():
            return JsonResponse({'erro': 'texto inválido'}, status=400)

        texto = form.cleaned_data['texto']
        resultados = []
        for trigger in Trigger.objects.filter(owner=request.user, ativo=True).order_by('prioridade'):
            casa = services._casa_palavras(trigger, services._normaliza(texto))
            resultados.append({'trigger': trigger.nome, 'casaria': casa})
        return JsonResponse({'resultados': resultados})


class TriggerLogListView(OwnedQuerysetMixin, ListView):
    model = TriggerLog
    template_name = 'triggers/logs.html'
    context_object_name = 'logs'

    def get_queryset(self):
        return TriggerLog.objects.filter(trigger__owner=self.request.user).select_related('trigger', 'contact')


class ScheduledMsgListView(LoginRequiredMixin, ListView):
    model = ScheduledMsg
    template_name = 'triggers/scheduled_list.html'
    context_object_name = 'agendadas'

    def get_queryset(self):
        return ScheduledMsg.objects.filter(
            contact__owner=self.request.user,
            status=ScheduledMsg.STATUS_PENDENTE,
        ).select_related('contact', 'instance', 'message')


class ScheduledMsgCreateForLeadView(LoginRequiredMixin, View):
    """Agenda um follow-up a partir da ficha do lead (crm:detail)."""

    def post(self, request, contact_pk):
        contact = get_object_or_404(Contact, pk=contact_pk, owner=request.user)
        form = ScheduledMsgForm(request.POST, owner=request.user)
        if form.is_valid():
            services.schedule_message(
                contact=contact,
                instance=form.cleaned_data['instance'],
                message=form.cleaned_data['message'],
                data_hora=form.cleaned_data['data_hora'],
            )
            messages.success(request, 'Follow-up agendado.')
        else:
            messages.error(request, 'Não foi possível agendar: verifique os campos.')

        from crm.models import Lead

        lead = Lead.objects.filter(contact=contact).first()
        return redirect('crm:detail', pk=lead.pk) if lead else redirect('contacts:list')


class ScheduledMsgCancelView(LoginRequiredMixin, View):
    def post(self, request, pk):
        agendada = get_object_or_404(ScheduledMsg, pk=pk, contact__owner=request.user)
        services.cancel_scheduled_message(agendada)
        messages.success(request, 'Follow-up cancelado.')
        return redirect('triggers:scheduled_list')


class ScheduledMsgRescheduleView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from django.utils import timezone
        from django.utils.dateparse import parse_datetime

        agendada = get_object_or_404(ScheduledMsg, pk=pk, contact__owner=request.user)
        nova_data = parse_datetime(request.POST.get('nova_data_hora', ''))
        if nova_data:
            if timezone.is_naive(nova_data):
                nova_data = timezone.make_aware(nova_data)
            services.reschedule_message(agendada, nova_data)
            messages.success(request, 'Follow-up reagendado.')
        else:
            messages.error(request, 'Informe uma data/hora válida.')
        return redirect('triggers:scheduled_list')
