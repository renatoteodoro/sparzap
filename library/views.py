from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from .forms import MessageFolderForm, MessageForm
from .models import Message, MessageFolder
from .services import render_message

PREVIEW_CONTEXT = {
    'nome': 'Fulano',
    'grupo': 'Ofertas Premium',
    'link': 'https://exemplo.com/oferta',
    'empresa': 'Sparzap',
}


class OwnedQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user)


class MessageListView(OwnedQuerysetMixin, ListView):
    model = Message
    template_name = 'library/list.html'
    context_object_name = 'messages_list'

    def get_queryset(self):
        queryset = super().get_queryset().select_related('folder')
        folder_id = self.request.GET.get('pasta')
        if folder_id:
            queryset = queryset.filter(folder_id=folder_id)
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(titulo__icontains=q)
        return queryset

    def get_context_data(self, **kwargs):
        from .models import MessageFolder

        context = super().get_context_data(**kwargs)
        context['folders'] = MessageFolder.objects.filter(owner=self.request.user)
        return context


class MessageCreateView(LoginRequiredMixin, CreateView):
    model = Message
    form_class = MessageForm
    template_name = 'library/form.html'
    success_url = reverse_lazy('library:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['owner'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, 'Mensagem criada.')
        return super().form_valid(form)


class MessageUpdateView(OwnedQuerysetMixin, UpdateView):
    model = Message
    form_class = MessageForm
    template_name = 'library/form.html'
    success_url = reverse_lazy('library:list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['owner'] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, 'Mensagem atualizada.')
        return super().form_valid(form)


class MessageDeleteView(OwnedQuerysetMixin, DeleteView):
    model = Message
    template_name = 'library/confirm_delete.html'
    success_url = reverse_lazy('library:list')


class MessagePreviewView(OwnedQuerysetMixin, View):
    model = Message

    def get(self, request, pk):
        message = get_object_or_404(self.get_queryset(), pk=pk)
        return JsonResponse({'preview': render_message(message, PREVIEW_CONTEXT, usar_variante=False)})


class MessageFolderCreateView(LoginRequiredMixin, CreateView):
    model = MessageFolder
    form_class = MessageFolderForm
    template_name = 'library/folder_form.html'
    success_url = reverse_lazy('library:list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, 'Pasta criada.')
        return super().form_valid(form)


class MessageFolderDeleteView(LoginRequiredMixin, DeleteView):
    model = MessageFolder
    template_name = 'library/folder_confirm_delete.html'
    success_url = reverse_lazy('library:list')

    def get_queryset(self):
        return MessageFolder.objects.filter(owner=self.request.user)
