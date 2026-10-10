"""
عميل Evolution API (v2) لربط واتساب بالمسح عبر QR وإرسال الرسائل.

كل الاستدعاءات من الخادم فقط: مفتاح الـ API لا يصل إلى المتصفح ولا يظهر في أي رسالة خطأ.
تُستخدم مكتبة Python القياسية (urllib) كي لا نضيف تبعية جديدة.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

QR_PREFIX = 'data:image/png;base64,'
INSTANCE_RE = re.compile(r'^[A-Za-z0-9_-]{1,60}$')


class WhatsAppError(Exception):
    """رسالتها عربية وآمنة للعرض (لا تحتوي المفتاح)."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def is_configured():
    return bool(settings.EVOLUTION_API_URL and settings.EVOLUTION_API_KEY and INSTANCE_RE.match(settings.EVOLUTION_INSTANCE or ''))


def _request(method, path, body=None):
    if not settings.WHATSAPP_ENABLED:
        raise WhatsAppError('ربط واتساب غير مفعّل (WHATSAPP_ENABLED)')
    if not is_configured():
        raise WhatsAppError('إعدادات Evolution API ناقصة. راجع ملف .env')
    base = settings.EVOLUTION_API_URL
    if urllib.parse.urlparse(base).scheme not in ('http', 'https'):
        raise WhatsAppError('رابط Evolution API غير صالح')
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={'apikey': settings.EVOLUTION_API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.EVOLUTION_API_TIMEOUT) as resp:
            raw = resp.read().decode('utf-8') or '{}'
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise WhatsAppError('مفتاح Evolution API غير صحيح', exc.code)
        if exc.code == 404:
            raise WhatsAppError('غير موجود', 404)
        raise WhatsAppError(f'رفض الخادم الطلب (HTTP {exc.code})', exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise WhatsAppError('تعذر الاتصال بخادم واتساب. تأكد أنه يعمل وأن الرابط صحيح')
    except ValueError:
        raise WhatsAppError('رد غير متوقع من خادم واتساب')


def _instance():
    return urllib.parse.quote(settings.EVOLUTION_INSTANCE, safe='')


def connection_state():
    """'open' (متصل) | 'connecting' | 'close' | 'not_found'."""
    try:
        data = _request('GET', f'/instance/connectionState/{_instance()}')
    except WhatsAppError as exc:
        if exc.status == 404:
            return 'not_found'
        raise
    inst = data.get('instance') or data
    state = inst.get('state') if isinstance(inst, dict) else None
    return state if state in ('open', 'connecting', 'close') else 'close'


def instance_info():
    """معلومات الرقم المربوط إن وُجدت: {'number','name'} أو {}."""
    try:
        data = _request('GET', f'/instance/fetchInstances?instanceName={_instance()}')
    except WhatsAppError:
        return {}
    item = data[0] if isinstance(data, list) and data else data if isinstance(data, dict) else {}
    item = item.get('instance', item) if isinstance(item, dict) else {}
    owner = item.get('ownerJid') or item.get('owner') or ''
    number = owner.split('@')[0] if owner else ''
    return {'number': re.sub(r'\D', '', number), 'name': item.get('profileName') or ''}


def create_instance():
    _request('POST', '/instance/create', {
        'instanceName': settings.EVOLUTION_INSTANCE, 'qrcode': True, 'integration': 'WHATSAPP-BAILEYS',
    })


def request_qr():
    """يطلب رمز QR جديدًا. يُنشئ المثيل إن لم يكن موجودًا. يُرجع {'qr': data-uri, 'pairing_code': str}."""
    state = connection_state()
    if state == 'not_found':
        create_instance()
    try:
        data = _request('GET', f'/instance/connect/{_instance()}')
    except WhatsAppError as exc:
        if exc.status == 404:
            create_instance()
            data = _request('GET', f'/instance/connect/{_instance()}')
        else:
            raise
    qr = data.get('base64') or ''
    # لا نمرّر للمتصفح إلا صورة PNG بصيغة data-uri المعروفة
    if qr and not qr.startswith(QR_PREFIX):
        qr = ''
    if qr and not re.fullmatch(r'[A-Za-z0-9+/=]+', qr[len(QR_PREFIX):]):
        qr = ''
    return {'qr': qr, 'pairing_code': data.get('pairingCode') or ''}


def logout():
    try:
        _request('DELETE', f'/instance/logout/{_instance()}')
    except WhatsAppError as exc:
        if exc.status != 404:
            raise


def normalize_number(raw, country=None):
    """رقم دولي بلا + ولا أصفار. يُرجع None إن كان غير صالح."""
    country = country or settings.WHATSAPP_DEFAULT_COUNTRY
    digits = re.sub(r'\D', '', str(raw or ''))
    if digits.startswith('00'):
        digits = digits[2:]
    elif digits.startswith('0'):
        digits = country + digits[1:]
    elif not digits.startswith(country) and len(digits) <= 9:
        digits = country + digits
    return digits if 8 <= len(digits) <= 15 else None


def send_text(number, text):
    to = normalize_number(number)
    if not to:
        raise WhatsAppError('رقم الجوال غير صالح')
    text = (text or '').strip()
    if not text:
        raise WhatsAppError('نص الرسالة فارغ')
    if len(text) > 4000:
        raise WhatsAppError('الرسالة أطول من 4000 حرف')
    return _request('POST', f'/message/sendText/{_instance()}', {'number': to, 'text': text})


WEBHOOK_EVENTS = ['MESSAGES_UPSERT', 'MESSAGES_UPDATE', 'SEND_MESSAGE', 'CONNECTION_UPDATE']


def get_webhook():
    """إعداد الـ webhook الحالي للمثيل: {'url','enabled'} أو {}."""
    try:
        data = _request('GET', f'/webhook/find/{_instance()}')
    except WhatsAppError:
        return {}
    if not isinstance(data, dict):
        return {}
    data = data.get('webhook', data)
    return {'url': data.get('url') or '', 'enabled': bool(data.get('enabled'))}


def set_webhook(url):
    return _request('POST', f'/webhook/set/{_instance()}', {
        'webhook': {'enabled': True, 'url': url, 'byEvents': False, 'base64': False, 'events': WEBHOOK_EVENTS},
    })


MAX_MEDIA_BYTES = 25 * 1024 * 1024



def fetch_media(wa_message_id):
    """يجلب ملف رسالة وسائط من Evolution. يُرجع (bytes, mimetype, file_name).

    الملف يأتي من مورد خارجي، فنحدّ الحجم قبل فك الترميز ونتحقق من صحة base64.
    """
    import base64
    import binascii

    if not wa_message_id:
        raise WhatsAppError('معرّف الرسالة غير متوفر')
    data = _request('POST', f'/chat/getBase64FromMediaMessage/{_instance()}', {
        'message': {'key': {'id': wa_message_id}}, 'convertToMp4': False,
    })
    if not isinstance(data, dict) or not data.get('base64'):
        raise WhatsAppError('لم يُرجع خادم واتساب الملف (قد لا يحتفظ بالرسالة)')
    raw = str(data['base64'])
    if raw.startswith('data:') and ',' in raw:
        raw = raw.split(',', 1)[1]
    if len(raw) > MAX_MEDIA_BYTES * 4 // 3 + 16:
        raise WhatsAppError('حجم الملف يتجاوز الحد المسموح (25 ميجابايت)')
    try:
        blob = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise WhatsAppError('الملف المستلم تالف')
    if not blob:
        raise WhatsAppError('الملف المستلم فارغ')
    if len(blob) > MAX_MEDIA_BYTES:
        raise WhatsAppError('حجم الملف يتجاوز الحد المسموح (25 ميجابايت)')
    mimetype = str(data.get('mimetype') or data.get('mimeType') or '').split(';')[0].strip().lower()[:100]
    return blob, mimetype, str(data.get('fileName') or '')[:255]
