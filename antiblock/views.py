from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View

from instances.models import Instance

from . import services
from .models import WarmupPlan


class WarmupListView(LoginRequiredMixin, View):
    template_name = 'antiblock/warmup.html'

    def get(self, request):
        instancias = Instance.objects.filter(owner=request.user)
        planos = {
            p.instance_id: p
            for p in WarmupPlan.objects.filter(
                instance__owner=request.user,
                status__in=[WarmupPlan.STATUS_EM_ANDAMENTO, WarmupPlan.STATUS_PAUSADO],
            )
        }
        linhas = [{'instance': i, 'plano': planos.get(i.id)} for i in instancias]
        return render(request, self.template_name, {'linhas': linhas})


class WarmupStartView(LoginRequiredMixin, View):
    def post(self, request, instance_pk):
        instance = get_object_or_404(Instance, pk=instance_pk, owner=request.user)
        services.start_warmup(instance, dias_total=int(request.POST.get('dias_total', 14)))
        messages.success(request, f'Aquecimento iniciado para "{instance.nome}".')
        return redirect('antiblock:warmup')


class WarmupPauseView(LoginRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(WarmupPlan, pk=pk, instance__owner=request.user)
        services.pause_warmup(plan)
        messages.success(request, 'Aquecimento pausado.')
        return redirect('antiblock:warmup')


class WarmupResumeView(LoginRequiredMixin, View):
    def post(self, request, pk):
        plan = get_object_or_404(WarmupPlan, pk=pk, instance__owner=request.user)
        services.resume_warmup(plan)
        messages.success(request, 'Aquecimento retomado.')
        return redirect('antiblock:warmup')
