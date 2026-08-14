from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import AIConfigForm
from .models import AIConfig


class OwnedQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class AIConfigListView(OwnedQuerysetMixin, ListView):
    model = AIConfig
    template_name = 'ai/list.html'
    context_object_name = 'configs'


class AIConfigCreateView(LoginRequiredMixin, CreateView):
    model = AIConfig
    form_class = AIConfigForm
    template_name = 'ai/form.html'
    success_url = reverse_lazy('ai:list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, 'Configuração de IA criada.')
        return super().form_valid(form)


class AIConfigUpdateView(OwnedQuerysetMixin, UpdateView):
    model = AIConfig
    form_class = AIConfigForm
    template_name = 'ai/form.html'
    success_url = reverse_lazy('ai:list')

    def form_valid(self, form):
        messages.success(self.request, 'Configuração de IA atualizada.')
        return super().form_valid(form)


class AIConfigDeleteView(OwnedQuerysetMixin, DeleteView):
    model = AIConfig
    template_name = 'ai/confirm_delete.html'
    success_url = reverse_lazy('ai:list')
