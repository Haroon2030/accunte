"""
البيانات الحية للواجهة: عدّادات الشريط الجانبي وآخر رسالة واردة (للتنبيه).

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


def _inbox():
    from apps.whatsapp.models import SLAConfiguration, SupplierConversation
    qs = SupplierConversation.objects.exclude(status='closed').filter(unread_count__gt=0)
    count = qs.count()
    if not count:
        return None
    limit = SLAConfiguration.current().first_response_minutes
    late = qs.filter(awaiting_reply_since__lt=timezone.now() - datetime.timedelta(minutes=limit)).exists()
    return _badge(count, 'danger' if late else 'info')


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


def _cases(user):
    from apps.reconciliation.models import ReconciliationCase as Case
    today = timezone.localdate()
    if get_role_type(user) == RT.ACCOUNTANT:
        mine = Case.objects.filter(assigned_accountant=user, status__in=Case.OPEN_STATUSES)
        return _badge(mine.count(), 'danger' if mine.filter(due_date__lt=today).exists() else 'info')
    late = Case.objects.filter(due_date__lt=today).exclude(status__in=Case.TERMINAL).count()
    return _badge(late, 'danger')


def _distribution():
    from apps.reconciliation.models import ReconciliationCase as Case
    return _badge(Case.objects.filter(status=Case.Status.READY_FOR_DISTRIBUTION).count(), 'warn')


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
        if key == 'inbox':
            b = _inbox()
        elif key == 'requests':
            b = _requests(user)
        elif key == 'cases':
            b = _cases(user)
        elif key == 'distribution':
            b = _distribution()
        elif key == 'proposals':
            b = _proposals(user)
        else:
            continue
        if b:
            out[key] = b
    return out


def latest_inbound():
    """آخر رسالة واردة (لإظهار تنبيه عند وصول جديدة)."""
    from apps.whatsapp.models import ConversationMessage
    m = (ConversationMessage.objects.filter(direction='in').select_related('conversation')
         .order_by('-id').first())
    if m is None:
        return None
    conv = m.conversation
    return {
        'id': m.pk, 'conversation_id': conv.pk, 'name': conv.display_name or f'+{conv.contact_number}',
        'preview': (m.body or f'[{m.get_kind_display()}]')[:90], 'url': f'/inbox/{conv.pk}/',
    }


@login_required
def badges_view(request):
    from apps.core.sidebar import visible_keys
    keys = visible_keys(request.user)
    data = {'badges': badge_counts(request.user, keys), 'inbox_latest': latest_inbound() if 'inbox' in keys else None}
    resp = JsonResponse(data)
    resp['Cache-Control'] = 'no-store'
    return resp
