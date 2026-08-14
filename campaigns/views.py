import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, View

from . import services
from .forms import CampaignForm
from .models import Campaign, CampaignContact
from .sse import campaign_progress_response


class OwnedQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class CampaignListView(OwnedQuerysetMixin, ListView):
    model = Campaign
    template_name = 'campaigns/list.html'
    context_object_name = 'campaigns'


class CampaignCreateView(LoginRequiredMixin, CreateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'campaigns/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['owner'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Campanha criada. Revise o público e inicie o disparo quando estiver pronta.')
        return response

    def get_success_url(self):
        return reverse_lazy('campaigns:detail', args=[self.object.pk])


class CampaignDetailView(OwnedQuerysetMixin, DetailView):
    model = Campaign
    template_name = 'campaigns/detail.html'
    context_object_name = 'campaign'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campanha = self.object
        contatos = campanha.campaign_contacts.all()
        context['contagem'] = {
            'total': contatos.count(),
            'pendente': contatos.filter(status=CampaignContact.STATUS_PENDENTE).count(),
            'enviada': contatos.filter(status=CampaignContact.STATUS_ENVIADA).count(),
            'respondida': contatos.filter(status=CampaignContact.STATUS_RESPONDIDA).count(),
            'falha': contatos.filter(status=CampaignContact.STATUS_FALHA).count(),
        }
        context['audiencia_prevista'] = services.audience_preview_count(campanha)
        context['campaign_contacts'] = contatos.select_related('contact')[:100]
        return context


class CampaignStartView(LoginRequiredMixin, View):
    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk, owner=request.user)
        services.start_campaign(campaign)
        messages.success(request, f'Campanha "{campaign.nome}" iniciada.')
        return redirect('campaigns:detail', pk=pk)


class CampaignPauseView(LoginRequiredMixin, View):
    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk, owner=request.user)
        services.pause_campaign(campaign)
        messages.success(request, f'Campanha "{campaign.nome}" pausada.')
        return redirect('campaigns:detail', pk=pk)


class CampaignResumeView(LoginRequiredMixin, View):
    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk, owner=request.user)
        services.resume_campaign(campaign)
        messages.success(request, f'Campanha "{campaign.nome}" retomada.')
        return redirect('campaigns:detail', pk=pk)


class CampaignCancelView(LoginRequiredMixin, View):
    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk, owner=request.user)
        services.cancel_campaign(campaign)
        messages.success(request, f'Campanha "{campaign.nome}" cancelada.')
        return redirect('campaigns:detail', pk=pk)


class CampaignProgressStreamView(LoginRequiredMixin, View):
    def get(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk, owner=request.user)
        return campaign_progress_response(campaign)


class CampaignReportExportView(LoginRequiredMixin, View):
    def get(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk, owner=request.user)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{campaign.nome}-relatorio.csv"'
        writer = csv.writer(response)
        writer.writerow(['numero', 'nome', 'status', 'enviado_em', 'respondido_em', 'erro'])
        for cc in campaign.campaign_contacts.select_related('contact'):
            writer.writerow(
                [
                    cc.contact.numero_e164,
                    cc.contact.nome,
                    cc.status,
                    cc.enviado_em,
                    cc.respondido_em,
                    cc.erro,
                ]
            )
        return response
