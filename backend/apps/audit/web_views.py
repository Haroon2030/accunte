from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from apps.core.access import AUDIT_VIEW_ROLES, role_required

from .models import AuditLog


@login_required
@role_required(*AUDIT_VIEW_ROLES)
def audit_list(request):
    qs = AuditLog.objects.all()
    action = request.GET.get('action', '')
    entity = request.GET.get('entity', '')
    q = request.GET.get('q', '').strip()
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    if action:
        qs = qs.filter(action=action)
    if entity:
        qs = qs.filter(entity_type=entity)
    if q:
        qs = qs.filter(Q(actor_username__icontains=q) | Q(entity_repr__icontains=q) | Q(entity_id=q))
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request, 'pages/audit/list.html', {
        'page_title': 'سجل التدقيق',
        'page_obj': page,
        'actions': AuditLog.Action.choices,
        'entities': AuditLog.objects.order_by().values_list('entity_type', flat=True).distinct(),
        'f': {'action': action, 'entity': entity, 'q': q, 'from': date_from, 'to': date_to},
    })
