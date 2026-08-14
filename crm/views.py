import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, View

from . import services
from .forms import LeadNoteForm
from .models import Lead, Stage


class KanbanView(LoginRequiredMixin, View):
    template_name = 'crm/kanban.html'

    def get(self, request):
        pipeline = services.get_or_create_default_pipeline(request.user)
        stages = pipeline.stages.order_by('ordem').prefetch_related('leads__contact')
        return render(request, self.template_name, {'pipeline': pipeline, 'stages': stages})


class LeadMoveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk, contact__owner=request.user)
        stage = get_object_or_404(Stage, pk=request.POST.get('stage_id'), pipeline=lead.pipeline)
        services.move_stage(lead, stage, motivo='kanban')
        return JsonResponse({'status': 'ok'})


class LeadListView(LoginRequiredMixin, ListView):
    model = Lead
    template_name = 'crm/list.html'
    context_object_name = 'leads'
    paginate_by = 50

    def get_queryset(self):
        queryset = Lead.objects.filter(contact__owner=self.request.user).select_related('contact', 'stage')
        stage_id = self.request.GET.get('etapa')
        if stage_id:
            queryset = queryset.filter(stage_id=stage_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pipeline = services.get_or_create_default_pipeline(self.request.user)
        context['stages'] = pipeline.stages.order_by('ordem')
        return context


class LeadDetailView(LoginRequiredMixin, DetailView):
    model = Lead
    template_name = 'crm/detail.html'
    context_object_name = 'lead'

    def get_queryset(self):
        return Lead.objects.filter(contact__owner=self.request.user)

    def get_context_data(self, **kwargs):
        from triggers.forms import ScheduledMsgForm

        context = super().get_context_data(**kwargs)
        context['note_form'] = LeadNoteForm()
        context['mensagens'] = self.object.mensagens.all()
        context['notas'] = self.object.notas.all()
        context['followup_form'] = ScheduledMsgForm(owner=self.request.user)
        return context


class LeadNoteCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        lead = get_object_or_404(Lead, pk=pk, contact__owner=request.user)
        form = LeadNoteForm(request.POST)
        if form.is_valid():
            form.instance.lead = lead
            form.save()
            messages.success(request, 'Anotação adicionada.')
        return redirect('crm:detail', pk=pk)


class LeadExportView(LoginRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="leads.csv"'
        writer = csv.writer(response)
        writer.writerow(['numero', 'nome', 'etapa', 'origem', 'entrou_na_etapa_em'])
        for lead in Lead.objects.filter(contact__owner=request.user).select_related('contact', 'stage'):
            writer.writerow(
                [lead.contact.numero_e164, lead.contact.nome, lead.stage.nome, lead.origem, lead.entrou_na_etapa_em]
            )
        return response
