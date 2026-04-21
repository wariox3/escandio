import hmac
import hashlib
import json
import logging
from decouple import config
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from mensajeria.servicios.webhook import WebhookServicio

logger = logging.getLogger(__name__)


def _firma_valida(cuerpo_raw, firma_header):
    """Valida firma X-Hub-Signature-256 con META_APP_SECRET si está configurado."""
    app_secret = config('META_APP_SECRET', default='')
    if not app_secret:
        return True
    if not firma_header or not firma_header.startswith('sha256='):
        return False
    esperada = 'sha256=' + hmac.new(
        app_secret.encode(),
        cuerpo_raw,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(esperada, firma_header)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def webhook_whatsapp(request):
    if request.method == 'GET':
        modo = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        verify_token_esperado = config('META_WEBHOOK_VERIFY_TOKEN', default='')
        if modo == 'subscribe' and token and token == verify_token_esperado:
            return HttpResponse(challenge, status=200)
        logger.warning(f'Webhook verify rechazado: modo={modo}')
        return HttpResponse('forbidden', status=403)

    cuerpo_raw = request.body
    firma = request.headers.get('X-Hub-Signature-256')
    if not _firma_valida(cuerpo_raw, firma):
        logger.warning('Webhook: firma HMAC inválida')
        return HttpResponse('invalid signature', status=403)

    try:
        payload = json.loads(cuerpo_raw.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'json inválido'}, status=400)

    try:
        resultados = WebhookServicio.procesar(payload)
        logger.info(f'Webhook procesado: {len(resultados)} eventos')
    except Exception as e:
        logger.exception(f'Webhook: error procesando payload: {e}')
        return JsonResponse({'error': 'procesamiento falló'}, status=500)

    return JsonResponse({'ok': True, 'eventos': len(resultados)}, status=200)
