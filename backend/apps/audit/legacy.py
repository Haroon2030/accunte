"""
جسر بين سجل المراجعة القديم (payments.AuditLog) وسجل التدقيق الجديد غير القابل للتعديل.
كل سطر جديد في القديم (يكتبه الـ API) يُنسخ تلقائيًا إلى الجديد، والأسطر القديمة تُنسخ بأمر backfill_payment_audit.
"""


from .models import AuditLog
from .services import sanitize

APPROVAL_STATUSES = {'first_approved', 'audited', 'final_approved', 'rejected'}


def mirror_legacy_row(legacy):
    """يُنشئ سجلًا جديدًا مقابلًا لسطر قديم. يُرجع None إن كان منسوخًا من قبل."""
    legacy_id = legacy.pk
    if AuditLog.objects.filter(entity_type='payments.PaymentRequest', new_state__legacy_id=legacy_id).exists():
        return None
    if legacy.new_status and legacy.new_status in APPROVAL_STATUSES:
        action = AuditLog.Action.APPROVAL
    elif legacy.old_status != legacy.new_status:
        action = AuditLog.Action.STATUS_CHANGE
    else:
        action = AuditLog.Action.OTHER
    user = legacy.user
    return AuditLog.objects.create(
        actor=user, actor_username=user.get_username()[:150] if user else '',
        action=action, entity_type='payments.PaymentRequest', entity_id=str(legacy.payment_request_id),
        entity_repr=f'طلب دفع #{legacy.payment_request_id}',
        previous_state={'status': legacy.old_status} if legacy.old_status else None,
        new_state=sanitize({
            'status': legacy.new_status, 'legacy_id': legacy_id, 'legacy_action': legacy.action,
            'legacy_created_at': legacy.created_at,
        }),
        reason=legacy.notes or '', ip_address=legacy.ip_address or None,
        user_agent=(legacy.user_agent or '')[:300], request_path='[legacy payments.AuditLog]',
    )


def on_legacy_saved(sender, instance, created, **kwargs):
    if created:
        mirror_legacy_row(instance)


def connect():
    from django.db.models.signals import post_save
    from apps.payments.models import AuditLog as LegacyAuditLog
    post_save.connect(on_legacy_saved, sender=LegacyAuditLog, dispatch_uid='audit_mirror_legacy_payment_log')



