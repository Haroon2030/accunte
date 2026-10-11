"""
تتبّع مسار حالة المطابقة: أين وصلت، وعند من تقف الآن، وكم بقيت في كل مرحلة، وسلسلة الأحداث الكاملة.
كل شيء يُشتق من StatusHistory وWorkAssignment والمستندات والفروقات، فلا حقول جديدة ولا ترحيلات.
"""
import datetime

from django.utils import timezone

from .models import ReconciliationCase as Case

S = Case.Status

# المسار الرئيسي: (المفتاح، التسمية، الأيقونة، الحالات التي تقع ضمنه)
STAGES = (
    ('intake', 'الاستلام والتجهيز', 'inbox', (S.NEW, S.PENDING_DOCS, S.READY_FOR_DISTRIBUTION)),
    ('assigned', 'الإسناد', 'user-check', (S.ASSIGNED,)),
    ('working', 'المطابقة', 'scale', (S.RECONCILING, S.WAITING_VENDOR, S.DISCREPANCY_FOUND)),
    ('review', 'المراجعة والاعتماد', 'badge-check', (S.PENDING_REVIEW, S.COMPLETED)),
    ('closed', 'الإغلاق', 'lock', (S.CLOSED,)),
)
STAGE_OF = {status: i for i, (_, _, _, statuses) in enumerate(STAGES) for status in statuses}

# وصف الحالات الفرعية داخل مرحلة «المطابقة»
SUBSTATE_NOTE = {
    S.WAITING_VENDOR: 'بانتظار رد المورد على الاستفسار',
    S.DISCREPANCY_FOUND: 'تم رصد فروقات وتجري تسويتها',
    S.RECONCILING: 'المحاسب يعمل على المطابقة',
}


def fmt_duration(delta):
    """مدة مقروءة بالعربية: «3 يوم 4 س» أو «25 د»."""
    secs = max(int(delta.total_seconds()), 0)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f'{d} يوم' + (f' {h} س' if h else '')
    if h:
        return f'{h} س' + (f' {m} د' if m else '')
    return f'{m} د' if m else 'أقل من دقيقة'


def _name(user):
    return (user.get_full_name() or user.username) if user else 'النظام'


def _holder(case, last_change):
    """من الجهة التي تقف عندها الحالة الآن، وما المطلوب منها."""
    s = case.status
    if s in (S.NEW, S.PENDING_DOCS):
        return {'title': 'فريق خدمة العملاء', 'name': _name(case.created_by), 'icon': 'headphones',
                'role': 'مُنشئ الحالة',
                'action': 'إرفاق كشف حساب المورد وتجهيز الحالة للإسناد'}
    if s == S.READY_FOR_DISTRIBUTION:
        return {'title': 'قائمة الإسناد', 'name': 'بانتظار مشرف الدعم', 'icon': 'git-fork', 'role': 'مشرف الدعم',
                'action': 'إسناد الحالة إلى محاسب'}
    if s in (S.ASSIGNED, S.RECONCILING, S.WAITING_VENDOR, S.DISCREPANCY_FOUND):
        action = {S.ASSIGNED: 'بدء المطابقة', S.RECONCILING: 'مطابقة الأرصدة وتسجيل النتيجة',
                  S.WAITING_VENDOR: f'متابعة رد المورد «{case.supplier.name}»',
                  S.DISCREPANCY_FOUND: 'تسوية الفروقات المرصودة'}[s]
        return {'title': 'المحاسب المسؤول', 'name': _name(case.assigned_accountant), 'icon': 'user-round',
                'role': 'محاسب', 'action': action}
    if s == S.PENDING_REVIEW:
        return {'title': 'المراجعة والاعتماد', 'name': 'المدير المالي', 'icon': 'search-check', 'role': 'مراجع',
                'action': 'مراجعة النتيجة والفروقات ثم الاعتماد أو الإعادة'}
    if s == S.COMPLETED:
        return {'title': 'الإغلاق', 'name': 'مشرف الدعم', 'icon': 'lock', 'role': 'مشرف',
                'action': 'إغلاق الملف أو إصدار أمر دفع'}
    return None


def build(case):
    """يُرجع كل ما تحتاجه صفحة التتبّع."""
    now = timezone.now()
    history = list(case.history.select_related('changed_by').order_by('created_at', 'id'))
    assignments = list(case.assignments.select_related('accountant', 'assigned_by').order_by('assigned_at', 'id'))
    documents = list(case.documents.select_related('uploaded_by').order_by('uploaded_at', 'id'))
    differences = list(case.differences.select_related('created_by').order_by('created_at', 'id'))

    # ── أين دخلت كل مرحلة ومتى ──
    entered, visited = {}, {STAGE_OF[S.NEW]}
    entered[STAGE_OF[S.NEW]] = case.created_at
    for h in history:
        if h.to_status in STAGE_OF:
            idx = STAGE_OF[h.to_status]
            visited.add(idx)
            entered.setdefault(idx, h.created_at)

    cancelled = case.status == S.CANCELLED
    if cancelled:
        reached = [STAGE_OF[h.from_status] for h in history if h.to_status == S.CANCELLED and h.from_status in STAGE_OF]
        current = max(reached) if reached else 0
    else:
        current = STAGE_OF[case.status]

    stages = []
    for i, (key, label, icon, statuses) in enumerate(STAGES):
        if cancelled and i == current:
            state = 'cancelled'
        elif i == current:
            state = 'done' if case.status == S.CLOSED else 'current'
        elif i < current:
            state = 'done'
        else:
            state = 'upcoming'
        stages.append({'key': key, 'label': label, 'icon': icon, 'state': state, 'at': entered.get(i)})
    done_count = sum(1 for s in stages if s['state'] == 'done')
    progress = 100 if case.status in (S.CLOSED,) else int((done_count + (0.5 if not cancelled else 0)) / len(STAGES) * 100)

    # ── منذ متى في الحالة الحالية ──
    last_change = history[-1].created_at if history else case.created_at
    ended = case.status in (S.CLOSED, S.CANCELLED)
    in_state = now - last_change if not ended else None
    total = (case.closed_at or now) - case.created_at

    # ── المدة في كل حالة ──
    spans = {}
    prev_status, prev_at = S.NEW, case.created_at
    for h in history:
        spans[prev_status] = spans.get(prev_status, datetime.timedelta()) + (h.created_at - prev_at)
        prev_status, prev_at = h.to_status, h.created_at
    if not ended:
        spans[prev_status] = spans.get(prev_status, datetime.timedelta()) + (now - prev_at)
    total_secs = sum((v.total_seconds() for v in spans.values()), 0) or 1
    durations = [{'label': S(st).label, 'text': fmt_duration(v), 'pct': round(v.total_seconds() / total_secs * 100),
                  'current': st == case.status and not ended}
                 for st, v in spans.items() if st not in (S.CLOSED, S.CANCELLED, S.COMPLETED) or v.total_seconds() > 60]

    # ── سلسلة الإسناد ──
    chain = []
    for a in assignments:
        end = a.ended_at or (None if a.is_active else a.assigned_at)
        chain.append({
            'accountant': _name(a.accountant), 'by': _name(a.assigned_by) if a.assigned_by else 'النظام',
            'at': a.assigned_at, 'ended_at': a.ended_at, 'active': a.is_active, 'note': a.note,
            'held': fmt_duration((end or now) - a.assigned_at),
        })

    # ── السجل الزمني الموحّد ──
    ev = [{'at': case.created_at, 'kind': 'create', 'icon': 'file-plus', 'title': 'فُتحت الحالة',
           'who': _name(case.created_by), 'detail': f'{case.supplier.name} · الفترة {case.period_start:%Y-%m-%d} → {case.period_end:%Y-%m-%d}'}]
    for h in history:
        kind = {S.CANCELLED: 'danger', S.COMPLETED: 'success', S.CLOSED: 'success',
                S.DISCREPANCY_FOUND: 'warn', S.WAITING_VENDOR: 'warn'}.get(h.to_status, 'move')
        ev.append({'at': h.created_at, 'kind': kind, 'icon': 'arrow-left-right',
                   'title': f'{h.from_label} ← {h.to_label}' if h.from_status else h.to_label,
                   'who': _name(h.changed_by), 'detail': h.reason})
    for a in assignments:
        ev.append({'at': a.assigned_at, 'kind': 'assign', 'icon': 'user-check',
                   'title': f'أُسندت إلى {_name(a.accountant)}', 'who': _name(a.assigned_by) if a.assigned_by else 'النظام',
                   'detail': a.note})
        if a.ended_at:
            ev.append({'at': a.ended_at, 'kind': 'move', 'icon': 'user-minus',
                       'title': f'انتهى إسناد {_name(a.accountant)}', 'who': '', 'detail': ''})
    for d in documents:
        ev.append({'at': d.uploaded_at, 'kind': 'doc', 'icon': 'paperclip',
                   'title': f'رُفع مستند: {d.get_doc_type_display()}', 'who': _name(d.uploaded_by), 'detail': d.original_name})
    for d in differences:
        ev.append({'at': d.created_at, 'kind': 'warn', 'icon': 'alert-triangle',
                   'title': f'سُجّل فرق: {d.get_kind_display()}', 'who': _name(d.created_by),
                   'detail': (d.document_ref + ' · ' if d.document_ref else '') + f'{d.difference:,.2f} ر.س'})
    ev.sort(key=lambda e: e['at'])
    prev = None
    for e in ev:
        e['since_prev'] = fmt_duration(e['at'] - prev) if prev and (e['at'] - prev).total_seconds() >= 60 else ''
        prev = e['at']
    ev.reverse()

    days_left = (case.due_date - timezone.localdate()).days if case.due_date and not case.is_terminal else None
    return {
        'stages': stages, 'progress': min(progress, 100), 'cancelled': cancelled,
        'holder': _holder(case, last_change), 'substate': SUBSTATE_NOTE.get(case.status, ''),
        'last_change': last_change, 'in_state': fmt_duration(in_state) if in_state is not None else '',
        'total': fmt_duration(total), 'durations': durations, 'chain': list(reversed(chain)), 'events': ev,
        'days_left': days_left, 'event_count': len(ev),
    }
