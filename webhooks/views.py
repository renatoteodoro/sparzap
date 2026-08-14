import json
import logging

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from instances.models import Instance

from .models import WebhookEvent
from .services import extract_message_id

logger = logging.getLogger('sparzap')


@csrf_exempt
@require_POST
def receive_webhook(request, instance_name):
    if settings.EVOLUTION_WEBHOOK_SECRET and request.GET.get('token') != settings.EVOLUTION_WEBHOOK_SECRET:
        logger.warning('webhook_token_invalido instance=%s', instance_name)
        return HttpResponseForbidden('token inválido')

    instance = get_object_or_404(Instance, evolution_instance_name=instance_name)

    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        logger.warning('webhook_payload_invalido instance=%s', instance_name)
        return JsonResponse({'erro': 'payload inválido'}, status=400)

    evento = payload.get('event', '')
    message_id = extract_message_id(payload)

    # Idempotência: mesmo message_id + evento já persistido -> não duplica.
    if message_id:
        existing = WebhookEvent.objects.filter(
            instance=instance,
            evento=evento,
            message_id=message_id,
        ).first()
        if existing:
            return JsonResponse({'status': 'duplicado'})

    event = WebhookEvent.objects.create(
        instance=instance,
        evento=evento,
        message_id=message_id,
        payload=payload,
    )

    from .tasks import process_webhook_event

    process_webhook_event.delay(event.id)

    return JsonResponse({'status': 'recebido'})
