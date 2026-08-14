import csv
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.generic import TemplateView, View

from . import backup
from .forms import ExportForm, ImportForm
from .models import Backup


class ReportsIndexView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        from crm import services as crm_services

        pipeline = crm_services.get_or_create_default_pipeline(user)
        context['funil'] = crm_services.stage_conversion(pipeline)

        from campaigns.models import Campaign, CampaignContact

        campanhas = []
        for campaign in Campaign.objects.filter(owner=user):
            contatos = campaign.campaign_contacts.all()
            total = contatos.count()
            enviadas = contatos.filter(status=CampaignContact.STATUS_ENVIADA).count()
            respondidas = contatos.filter(status=CampaignContact.STATUS_RESPONDIDA).count()
            campanhas.append(
                {
                    'campanha': campaign,
                    'total': total,
                    'enviadas': enviadas,
                    'respondidas': respondidas,
                    'taxa_resposta': round(100 * respondidas / total, 1) if total else 0,
                }
            )
        context['campanhas'] = campanhas

        from antiblock.models import DailyLimit
        from instances.models import Instance

        desde = timezone.localdate() - timezone.timedelta(days=30)
        context['entregas_por_instancia'] = (
            DailyLimit.objects.filter(instance__owner=user, data__gte=desde)
            .values('instance__nome')
            .order_by('instance__nome')
        )
        context['instancias'] = Instance.objects.filter(owner=user)
        return context


class DeliveryReportExportView(LoginRequiredMixin, View):
    def get(self, request):
        from antiblock.models import DailyLimit

        desde = timezone.localdate() - timezone.timedelta(days=30)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="entregas-30dias.csv"'
        writer = csv.writer(response)
        writer.writerow(['instancia', 'data', 'enviadas'])
        for row in DailyLimit.objects.filter(instance__owner=request.user, data__gte=desde).select_related('instance'):
            writer.writerow([row.instance.nome, row.data, row.enviadas])
        return response


class BackupView(LoginRequiredMixin, View):
    template_name = 'reports/backup.html'

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                'export_form': ExportForm(),
                'import_form': ImportForm(owner=request.user),
                'backups': Backup.objects.filter(owner=request.user)[:10],
            },
        )


class BackupExportView(LoginRequiredMixin, View):
    def post(self, request):
        form = ExportForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Selecione ao menos uma seção para exportar.')
            return redirect('reports:backup')

        secoes = form.cleaned_data['secoes']
        dados = backup.export_config(request.user, secoes=secoes)
        Backup.objects.create(
            owner=request.user,
            tipo=Backup.TIPO_COMPLETO if set(secoes) == set(backup.SECOES_DISPONIVEIS) else Backup.TIPO_SELETIVO,
            secoes=','.join(secoes),
            conteudo=dados,
        )

        response = HttpResponse(json.dumps(dados, ensure_ascii=False, indent=2), content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="sparzap-backup-{timezone.now():%Y%m%d-%H%M}.json"'
        return response


class BackupImportView(LoginRequiredMixin, View):
    def post(self, request):
        form = ImportForm(request.POST, request.FILES, owner=request.user)
        if not form.is_valid():
            messages.error(request, 'Verifique o arquivo e a instância de destino.')
            return redirect('reports:backup')

        try:
            dados = json.loads(form.cleaned_data['arquivo'].read())
        except (ValueError, UnicodeDecodeError):
            messages.error(request, 'O arquivo não é um JSON válido.')
            return redirect('reports:backup')

        valido, erro = backup.validate_config(dados)
        if not valido:
            messages.error(request, erro)
            return redirect('reports:backup')

        relatorio = backup.import_config(
            request.user,
            form.cleaned_data['target_instance'],
            dados,
            conflito=form.cleaned_data['conflito'],
        )
        messages.success(
            request,
            f"Importação concluída: {relatorio['criados']} criados, "
            f"{relatorio['atualizados']} atualizados, {relatorio['ignorados']} ignorados.",
        )
        return redirect('reports:backup')
