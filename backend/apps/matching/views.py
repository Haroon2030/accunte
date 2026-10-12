"""واجهات JSON للمطابقة والشكاوى."""
import re

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.api import ApiError, body, endpoint
from apps.accounts.models import UserProfile
from apps.accounts.services import serialize_user

from . import services
from .models import Attachment, Seen
from .storage import serve_file

Role = UserProfile.Role
User = get_user_model()
SEEN_KEY = re.compile(r'^(MT|SH)-\d{4}-\d{4,}:(supplier|matcher|manager)$')


@endpoint(methods=('GET',))
def bootstrap(request):
    """كل ما تحتاجه الواجهة بعد الدخول وعند التحديث الدوري: المستخدم، الطلبات، الشكاوى، (المستخدمون للمدير)، المقروء."""
    user = request.user
    seen = {s.key: int(s.at.timestamp() * 1000) for s in Seen.objects.filter(user=user)}
    payload = {
        'user': serialize_user(user), 'requests': services.requests_payload(user),
        'complaints': services.complaints_payload(user), 'seen': seen, 'serverTime': timezone.now().isoformat(),
    }
    if user.profile.role == Role.ADMIN:
        users = User.objects.select_related('profile').filter(profile__isnull=False).order_by('first_name', 'username')
        payload['users'] = [serialize_user(u) for u in users]
    return JsonResponse(payload)


def _files(request, field='files'):
    return request.FILES.getlist(field)


@endpoint(methods=('POST',), roles=(Role.SUPPLIER,))
def request_create(request):
    data = body(request)
    req = services.create_request(request.user, data.get('period'), data.get('notes'), request.FILES.get('file'))
    req = services.visible_requests(request.user).select_related('matcher', 'statement') \
        .prefetch_related('messages__attachments').get(pk=req.pk)
    return JsonResponse({'request': services.serialize_request(req)}, status=201)


def _reload_request(user, code):
    return (services.visible_requests(user).select_related('matcher', 'statement')
            .prefetch_related('messages__attachments').get(code=code))


def _reload_complaint(user, code):
    return (services.visible_complaints(user).select_related('related')
            .prefetch_related('messages__attachments').get(code=code))


@endpoint(methods=('POST',))
def request_advance(request, code):
    req = services.advance_request(request.user, code)
    return JsonResponse({'request': services.serialize_request(_reload_request(request.user, req.code))})


@endpoint(methods=('POST',))
def request_message(request, code):
    data = body(request)
    services.post_request_message(request.user, code, data.get('text'), data.get('from'), _files(request))
    return JsonResponse({'request': services.serialize_request(_reload_request(request.user, code))}, status=201)


@endpoint(methods=('POST',), roles=(Role.SUPPLIER,))
def complaint_create(request):
    data = body(request)
    c = services.create_complaint(request.user, data.get('category'), data.get('subject'), data.get('body'),
                                  data.get('related') or '', _files(request))
    return JsonResponse({'complaint': services.serialize_complaint(_reload_complaint(request.user, c.code))}, status=201)


@endpoint(methods=('POST',))
def complaint_advance(request, code):
    c = services.advance_complaint(request.user, code)
    return JsonResponse({'complaint': services.serialize_complaint(_reload_complaint(request.user, c.code))})


@endpoint(methods=('POST',))
def complaint_message(request, code):
    data = body(request)
    services.post_complaint_message(request.user, code, data.get('text'), data.get('from'), _files(request))
    return JsonResponse({'complaint': services.serialize_complaint(_reload_complaint(request.user, code))}, status=201)


@endpoint(methods=('POST',))
def mark_seen(request):
    key = str(body(request).get('key') or '')
    if not SEEN_KEY.match(key):
        raise ApiError('مفتاح غير صالح.')
    Seen.objects.update_or_create(user=request.user, key=key, defaults={'at': timezone.now()})
    return JsonResponse({'ok': True})


@endpoint(methods=('GET',))
def attachment_download(request, pk):
    att = get_object_or_404(Attachment.objects.select_related('message'), pk=pk)
    if not services.attachment_visible_to(request.user, att):
        raise ApiError('الملف غير موجود.', 404)
    return serve_file(att.file, att.name)
