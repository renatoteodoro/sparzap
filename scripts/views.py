from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from . import services
from .forms import ScriptForm, ScriptStepForm, TestRunForm
from .models import Script, ScriptRun, ScriptStep


class OwnedQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class ScriptListView(OwnedQuerysetMixin, ListView):
    model = Script
    template_name = 'scripts/list.html'
    context_object_name = 'scripts'


class ScriptCreateView(LoginRequiredMixin, CreateView):
    model = Script
    form_class = ScriptForm
    template_name = 'scripts/form.html'

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Script criado. Agora adicione os passos.')
        return response

    def get_success_url(self):
        return reverse_lazy('scripts:detail', args=[self.object.pk])


class ScriptUpdateView(OwnedQuerysetMixin, UpdateView):
    model = Script
    form_class = ScriptForm
    template_name = 'scripts/form.html'

    def get_success_url(self):
        return reverse_lazy('scripts:detail', args=[self.object.pk])


class ScriptDeleteView(OwnedQuerysetMixin, DeleteView):
    model = Script
    template_name = 'scripts/confirm_delete.html'
    success_url = reverse_lazy('scripts:list')


class ScriptDetailView(OwnedQuerysetMixin, DetailView):
    model = Script
    template_name = 'scripts/detail.html'
    context_object_name = 'script'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['step_form'] = ScriptStepForm(script=self.object, owner=self.request.user)
        context['test_form'] = TestRunForm(owner=self.request.user)
        return context


class ScriptDuplicateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        original = get_object_or_404(Script, pk=pk, owner=request.user)
        copia = Script.objects.create(owner=request.user, nome=f'{original.nome} (cópia)', descricao=original.descricao)
        mapa_passos = {}
        for step in original.steps.order_by('ordem'):
            novo = ScriptStep.objects.create(
                script=copia,
                ordem=step.ordem,
                tipo=step.tipo,
                message=step.message,
                delay_s=step.delay_s,
                timeout_h=step.timeout_h,
                condicao_contem=step.condicao_contem,
                etapa_destino=step.etapa_destino,
                usar_ia=step.usar_ia,
                ia_config=step.ia_config,
                condicao_ia_descricao=step.condicao_ia_descricao,
            )
            mapa_passos[step.id] = novo
        for step in original.steps.all():
            if step.proximo_passo_id:
                novo = mapa_passos[step.id]
                novo.proximo_passo = mapa_passos.get(step.proximo_passo_id)
                novo.save(update_fields=['proximo_passo'])
        messages.success(request, f'Script duplicado como "{copia.nome}".')
        return redirect('scripts:detail', pk=copia.pk)


class ScriptStepCreateView(LoginRequiredMixin, View):
    def post(self, request, script_pk):
        script = get_object_or_404(Script, pk=script_pk, owner=request.user)
        form = ScriptStepForm(request.POST, script=script, owner=request.user)
        if form.is_valid():
            form.instance.script = script
            form.save()
            messages.success(request, 'Passo adicionado.')
        else:
            messages.error(request, f'Não foi possível adicionar o passo: {form.errors.as_text()}')
        return redirect('scripts:detail', pk=script.pk)


class ScriptStepDeleteView(LoginRequiredMixin, View):
    def post(self, request, script_pk, pk):
        step = get_object_or_404(ScriptStep, pk=pk, script_id=script_pk, script__owner=request.user)
        script_pk = step.script_id
        step.delete()
        messages.success(request, 'Passo removido.')
        return redirect('scripts:detail', pk=script_pk)


class ScriptTestRunView(LoginRequiredMixin, View):
    def post(self, request, pk):
        script = get_object_or_404(Script, pk=pk, owner=request.user)
        form = TestRunForm(request.POST, owner=request.user)
        if form.is_valid():
            run = services.run_test(script, form.cleaned_data['contact'], form.cleaned_data['instance'])
            # Um teste que falha nao pode sair como mensagem verde de sucesso:
            # antes, o usuario via "✅ Execução de teste iniciada (status: Erro)"
            # sem nenhuma pista do motivo, que fica em `run.erro`.
            if run.status == ScriptRun.STATUS_ERRO:
                messages.error(request, f'O teste falhou: {services.explicar_erro(run)}')
            else:
                messages.success(request, f'Execução de teste iniciada (status: {run.get_status_display()}).')
        else:
            messages.error(request, 'Selecione um contato e uma instância válidos.')
        return redirect('scripts:detail', pk=pk)
