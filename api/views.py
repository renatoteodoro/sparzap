from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from campaigns.models import Campaign, CampaignContact
from campaigns.services import start_campaign
from contacts.models import Contact
from contacts.utils import normalize_br_number
from crm.models import Lead
from instances.models import Instance

from .serializers import (
    CampaignReportSerializer,
    CampaignSerializer,
    ContactSerializer,
    InstanceSerializer,
    LeadSerializer,
    ScheduleMessageSerializer,
)


class OwnedModelViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        return self.queryset.filter(**{self.owner_lookup: self.request.user})


class InstanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InstanceSerializer
    queryset = Instance.objects.all()

    def get_queryset(self):
        return Instance.objects.filter(owner=self.request.user)


class CampaignViewSet(OwnedModelViewSet):
    serializer_class = CampaignSerializer
    queryset = Campaign.objects.all()
    owner_lookup = 'owner'

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        campaign = self.get_object()
        contatos = campaign.campaign_contacts.all()
        dados = {
            'total': contatos.count(),
            'pendente': contatos.filter(status=CampaignContact.STATUS_PENDENTE).count(),
            'enviada': contatos.filter(status=CampaignContact.STATUS_ENVIADA).count(),
            'respondida': contatos.filter(status=CampaignContact.STATUS_RESPONDIDA).count(),
            'falha': contatos.filter(status=CampaignContact.STATUS_FALHA).count(),
        }
        return Response(CampaignReportSerializer(dados).data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in (Campaign.STATUS_RASCUNHO, Campaign.STATUS_PAUSADA):
            return Response(
                {'erro': f'Campanha está "{campaign.status}", não pode ser iniciada.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        start_campaign(campaign)
        return Response({'status': 'iniciada'})


class ContactViewSet(OwnedModelViewSet):
    serializer_class = ContactSerializer
    queryset = Contact.objects.all()
    owner_lookup = 'owner'

    def perform_create(self, serializer):
        numero = normalize_br_number(serializer.validated_data['numero_e164'])
        if not numero:
            raise ValidationError({'numero_e164': 'Número inválido.'})
        contato, _ = Contact.objects.update_or_create(
            owner=self.request.user,
            numero_e164=numero,
            defaults={'nome': serializer.validated_data.get('nome', '')},
        )
        serializer.instance = contato


class LeadViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LeadSerializer
    queryset = Lead.objects.all()

    def get_queryset(self):
        return Lead.objects.filter(contact__owner=self.request.user).select_related('contact', 'stage')


class ScheduleMessageView(viewsets.ViewSet):
    serializer_class = ScheduleMessageSerializer

    def create(self, request):
        from library.models import Message
        from triggers.services import schedule_message

        serializer = ScheduleMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        numero = normalize_br_number(data['numero'])
        if not numero:
            return Response({'erro': 'numero inválido'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            instance = Instance.objects.get(id=data['instance_id'], owner=request.user)
            message = Message.objects.get(id=data['message_id'], owner=request.user)
        except (Instance.DoesNotExist, Message.DoesNotExist):
            return Response({'erro': 'instance_id ou message_id inválido'}, status=status.HTTP_400_BAD_REQUEST)

        contact, _ = Contact.objects.get_or_create(owner=request.user, numero_e164=numero)
        agendada = schedule_message(contact, instance, message, data['data_hora'])
        return Response({'id': agendada.id, 'status': agendada.status}, status=status.HTTP_201_CREATED)
