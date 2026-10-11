"""
البيانات الحية للواجهة: عدّادات الشريط الجانبي.

كل عدّاد استعلام COUNT واحد مفهرس، ولا يُحسب إلا للعناصر التي يراها المستخدم. يُستدعى عند فتح الصفحة،
ثم يُحدّثه المتصفح دوريًا من /live/badges/ بلا إعادة تحميل.
"""
import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone

from apps.core.access import get_role_type
from apps.core.models import Role

RT = Role.RoleType


def _badge(count, tone='info'):
    return {'count': int(count), 'tone': tone} if count else None






def _requests(user):
    from apps.servicedesk import services
    from apps.servicedesk.models import ServiceRequest as SR
    now = timezone.now()
    open_qs = services.visible_requests(user).filter(status__in=SR.OPEN)
    if services.is_supervisor(user) or get_role_type(user) == RT.ACCOUNTANT:
        mine = open_qs.filter(assigned_to=user)
        waiting = open_qs.filter(assigned_to__isnull=True)
        total = mine.count() + waiting.count()
        late = open_qs.filter(due_at__lt=now).filter(assigned_to=user).exists() or \
            waiting.filter(due_at__lt=now).exists()
        return _badge(total, 'danger' if late else 'info')
    return None


def _my_tasks(user):
    from apps.servicedesk.models import ServiceRequest as SR
    mine = SR.objects.filter(assigned_to=user, status__in=SR.OPEN)
    count = mine.count()
    late = mine.filter(due_at__lt=timezone.now()).exists()
    return _badge(count, 'danger' if late else 'info')


def _proposals(user):
    from apps.proposals.models import PaymentProposal as P
    S = P.Status
    role = get_role_type(user)
    pending = P.objects.filter(status__in=(S.SUBMITTED, S.PENDING_REVIEW))
    if role in (RT.CFO, RT.ADMIN):          # بانتظار قراره + معتمد بانتظار الصرف والتأكيد
        waiting = P.objects.filter(status__in=(S.APPROVED, S.DISPATCHED))
        return _badge(pending.count() + waiting.count(), 'warn')
    if role in (RT.ACCOUNTANT, RT.CS_SUPERVISOR):          # مقترحاتي المطلوب استيضاحها
        return _badge(P.objects.filter(created_by=user, status=S.NEEDS_INFO).count(), 'warn')
    return None


def badge_counts(user, keys):
    """{key: {'count','tone'}} للعناصر ذات العدّاد من بين keys فقط."""
    out = {}
    for key in keys:
        if key == 'requests':
            b = _requests(user)
        elif key == 'my_tasks':
            b = _my_tasks(user)
        elif key == 'proposals':
            b = _proposals(user)
        else:
            continue
        if b:
            out[key] = b
    return out



@login_required
def badges_view(request):
    from apps.core.sidebar import visible_keys
    keys = visible_keys(request.user)
    data = {'badges': badge_counts(request.user, keys)}
    resp = JsonResponse(data)
    resp['Cache-Control'] = 'no-store'
    return resp
