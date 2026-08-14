import json
import time

from django.http import StreamingHttpResponse


def campaign_progress_stream(campaign, intervalo_s=2, max_iteracoes=1800):
    """
    Gerador SSE com o progresso da campanha. Encerra sozinho quando a
    campanha sai de 'em_andamento' ou após `max_iteracoes` (~1h no default),
    para não manter uma conexão aberta indefinidamente no dev server.
    """
    from .models import CampaignContact

    for _ in range(max_iteracoes):
        campaign.refresh_from_db()
        contagem = {
            'status': campaign.status,
            'pendente': campaign.campaign_contacts.filter(status=CampaignContact.STATUS_PENDENTE).count(),
            'enviada': campaign.campaign_contacts.filter(status=CampaignContact.STATUS_ENVIADA).count(),
            'respondida': campaign.campaign_contacts.filter(status=CampaignContact.STATUS_RESPONDIDA).count(),
            'falha': campaign.campaign_contacts.filter(status=CampaignContact.STATUS_FALHA).count(),
        }
        yield f'data: {json.dumps(contagem)}\n\n'

        if campaign.status not in (campaign.STATUS_EM_ANDAMENTO,):
            break
        time.sleep(intervalo_s)


def campaign_progress_response(campaign, **kwargs):
    response = StreamingHttpResponse(
        campaign_progress_stream(campaign, **kwargs),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
