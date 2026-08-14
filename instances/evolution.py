"""Cliente HTTP para a Evolution API v2 — unica porta de entrada/saida do
Sparzap para o WhatsApp. Ver docs/evolution.md para o contrato de payloads.
"""

import logging
import time

from django.conf import settings

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('sparzap')

# Retry automático só em métodos idempotentes (leitura) — POST de envio de
# mensagem NUNCA é retentado aqui, para não arriscar disparo duplicado; a
# idempotência de envio é responsabilidade do Celery/negócio (Sprint 8).
_SAFE_RETRY = Retry(
    total=2,
    backoff_factor=0.5,
    status_forcelist=[502, 503, 504],
    allowed_methods=frozenset(['GET']),
)

# Endpoints de grupo da Evolution buscam metadados de CADA grupo, um a um,
# direto do WhatsApp — numa conta real com dezenas de grupos isso passa
# facilmente de 90s (medido: 93s para ~40 grupos), e não há cache que
# ajude: o custo se repete a cada chamada. O timeout padrão de 10s derrubava
# a sincronização sempre. Estes endpoints usam um timeout próprio e
# **sem retry**: retentar uma chamada de 90s multiplicaria a espera sem
# nenhuma chance real de sucesso.
TIMEOUT_LENTO = 180


class EvolutionError(Exception):
    """Erro genérico de comunicação com a Evolution API."""


class EvolutionUnavailable(EvolutionError):
    """Timeout ou erro de rede/5xx ao chamar a Evolution API."""


class EvolutionAuthError(EvolutionError):
    """apikey inválida ou instância não autorizada (401/403)."""


class EvolutionRateLimited(EvolutionError):
    """A Evolution respondeu 429 — o AntiBlock deve pausar a instância."""


class EvolutionClient:
    """
    Wrapper fino sobre a API HTTP da Evolution. Sem retry automático aqui
    para chamadas de escrita (envio de mensagem) — retry/backoff de negócio
    fica no Celery (Sprint 8); leitura (status, participantes) pode reter.
    """

    def __init__(self, base_url=None, api_key=None, timeout=10):
        self.base_url = (base_url or settings.EVOLUTION_BASE_URL).rstrip('/')
        self.api_key = api_key or settings.EVOLUTION_API_KEY
        self.timeout = timeout
        self.session = requests.Session()
        self.session.mount('http://', HTTPAdapter(max_retries=_SAFE_RETRY))
        self.session.mount('https://', HTTPAdapter(max_retries=_SAFE_RETRY))

        # sessão sem retry, para os endpoints lentos (ver TIMEOUT_LENTO)
        self.session_sem_retry = requests.Session()

    def _headers(self):
        return {'apikey': self.api_key, 'Content-Type': 'application/json'}

    def _request(self, method, path, timeout=None, retry=True, **kwargs):
        url = f'{self.base_url}{path}'
        session = self.session if retry else self.session_sem_retry
        started = time.monotonic()
        try:
            response = session.request(
                method, url, headers=self._headers(), timeout=timeout or self.timeout, **kwargs
            )
        except requests.exceptions.RequestException as exc:
            logger.warning(
                'evolution_request_failed method=%s path=%s error=%s latency_ms=%.0f',
                method,
                path,
                exc,
                (time.monotonic() - started) * 1000,
            )
            raise EvolutionUnavailable(str(exc)) from exc

        logger.info(
            'evolution_request method=%s path=%s status=%s latency_ms=%.0f',
            method,
            path,
            response.status_code,
            (time.monotonic() - started) * 1000,
        )

        if response.status_code in (401, 403):
            raise EvolutionAuthError(f'{response.status_code}: {response.text[:200]}')
        if response.status_code == 429:
            raise EvolutionRateLimited(response.text[:200])
        if response.status_code >= 500:
            raise EvolutionUnavailable(f'{response.status_code}: {response.text[:200]}')
        if response.status_code >= 400:
            raise EvolutionError(f'{response.status_code}: {response.text[:200]}')

        if response.content:
            try:
                return response.json()
            except ValueError:
                return {}
        return {}

    # --- Instância -----------------------------------------------------

    def create_instance(self, instance_name):
        return self._request(
            'POST',
            '/instance/create',
            json={
                'instanceName': instance_name,
                'qrcode': True,
                'integration': 'WHATSAPP-BAILEYS',
            },
        )

    def connect(self, instance_name):
        return self._request('GET', f'/instance/connect/{instance_name}')

    def connection_state(self, instance_name):
        return self._request('GET', f'/instance/connectionState/{instance_name}')

    def delete_instance(self, instance_name):
        return self._request('DELETE', f'/instance/delete/{instance_name}')

    # --- Mensagens -------------------------------------------------------

    def send_text(self, instance_name, number, text):
        return self._request(
            'POST',
            f'/message/sendText/{instance_name}',
            json={
                'number': number,
                'text': text,
            },
        )

    def send_media(self, instance_name, number, media_url, media_type='image', caption=''):
        return self._request(
            'POST',
            f'/message/sendMedia/{instance_name}',
            json={
                'number': number,
                'mediatype': media_type,
                'media': media_url,
                'caption': caption,
            },
        )

    def send_audio(self, instance_name, number, audio_url):
        return self._request(
            'POST',
            f'/message/sendWhatsAppAudio/{instance_name}',
            json={
                'number': number,
                'audio': audio_url,
            },
        )

    def send_mention(self, instance_name, group_jid, text):
        return self._request(
            'POST',
            f'/group/sendMention/{instance_name}',
            json={
                'groupJid': group_jid,
                'text': text,
            },
        )

    # --- Grupos ----------------------------------------------------------

    def fetch_all_groups(self, instance_name, get_participants=False):
        return self._request(
            'GET',
            f'/group/fetchAllGroups/{instance_name}',
            params={'getParticipants': str(get_participants).lower()},
            timeout=TIMEOUT_LENTO,
            retry=False,
        )

    def fetch_all_participants(self, instance_name, group_jid):
        # v2.3.7: o caminho é /group/participants/{instance}?groupJid=...
        # O formato antigo (/group/fetchAllParticipants/{instance}/{jid})
        # responde 404 — confirmado contra uma instância real.
        return self._request(
            'GET',
            f'/group/participants/{instance_name}',
            params={'groupJid': group_jid},
            timeout=TIMEOUT_LENTO,
            retry=False,
        )

    def update_participant(self, instance_name, group_jid, action, participants):
        return self._request(
            'POST',
            f'/group/updateParticipant/{instance_name}',
            json={
                'groupJid': group_jid,
                'action': action,
                'participants': participants,
            },
        )

    # --- Webhook -----------------------------------------------------------

    def set_webhook(self, instance_name, webhook_url, events):
        return self._request(
            'POST',
            f'/webhook/set/{instance_name}',
            json={
                'webhook': {
                    'url': webhook_url,
                    'enabled': True,
                    'events': events,
                },
            },
        )


EVOLUTION_WEBHOOK_EVENTS = [
    'MESSAGES_UPSERT',
    'MESSAGES_UPDATE',
    'CONNECTION_UPDATE',
    'CONTACTS_UPSERT',
]
