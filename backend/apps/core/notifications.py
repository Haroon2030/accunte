"""
خدمة الإشعارات
"""

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Notification, Role
from apps.payments.models import PaymentRequest


def _active_users():
    return User.objects.filter(is_active=True).select_related('profile', 'profile__role')


def _users_with_perm(perm):
    users = []
    for user in _active_users():
        if user.has_perm(perm):
            users.append(user)
    return users


def _admin_users():
    users = []
    for user in _active_users():
        if user.is_superuser:
            users.append(user)
            continue
        profile = getattr(user, 'profile', None)
        if profile and profile.role and profile.role.role_type == Role.RoleType.ADMIN:
            users.append(user)
    return users


def _unique_users(*user_lists, exclude=None):
    seen = set()
    result = []
    exclude_id = getattr(exclude, 'pk', None)
    for user_list in user_lists:
        for user in user_list:
            if user.pk in seen or user.pk == exclude_id:
                continue
            seen.add(user.pk)
            result.append(user)
    return result


def _create_notifications(recipients, *, title, message, link='', category=Notification.Category.PAYMENT):
    if not recipients:
        return
    Notification.objects.bulk_create([
        Notification(
            recipient=user,
            category=category,
            title=title,
            message=message,
            link=link,
        )
        for user in recipients
    ])


def _payment_link(payment):
    return reverse('payments:detail', args=[payment.pk])


def notify_payment_created(payment, actor):
    """إشعار عند إنشاء طلب دفع جديد أو تقديمه."""
    link = _payment_link(payment)
    if payment.status == PaymentRequest.Status.PROPOSED:
        recipients = _unique_users(
            _users_with_perm('payments.can_first_approve'),
            _admin_users(),
            exclude=actor,
        )
        _create_notifications(
            recipients,
            title='طلب دفع جديد بانتظار الموافقة',
            message=f'تم تقديم طلب دفع #{payment.pk} لفرع {payment.branch.name} ويحتاج موافقة مبدئية.',
            link=link,
        )
    elif payment.status == PaymentRequest.Status.DRAFT:
        recipients = _unique_users(_admin_users(), exclude=actor)
        _create_notifications(
            recipients,
            title='مسودة طلب دفع جديدة',
            message=f'تم إنشاء مسودة طلب دفع #{payment.pk} لفرع {payment.branch.name}.',
            link=link,
        )


def notify_payment_status_changed(payment, old_status, new_status, actor):
    """إشعار عند تغيير حالة طلب الدفع."""
    if old_status == new_status:
        return

    link = _payment_link(payment)
    status_label = payment.get_status_display()
    actor_name = actor.get_full_name() or actor.username

    if new_status == PaymentRequest.Status.PROPOSED:
        recipients = _unique_users(
            _users_with_perm('payments.can_first_approve'),
            _admin_users(),
            exclude=actor,
        )
        _create_notifications(
            recipients,
            title='طلب دفع بانتظار الموافقة المبدئية',
            message=f'طلب الدفع #{payment.pk} ({payment.branch.name}) جاهز للمراجعة والموافقة المبدئية.',
            link=link,
        )
        return

    if new_status == PaymentRequest.Status.FIRST_APPROVED:
        recipients = _unique_users(
            _users_with_perm('payments.can_audit'),
            _admin_users(),
            exclude=actor,
        )
        _create_notifications(
            recipients,
            title='طلب دفع بانتظار التدقيق',
            message=f'تمت الموافقة المبدئية على طلب #{payment.pk} وهو الآن بانتظار التدقيق المالي.',
            link=link,
        )
        return

    if new_status == PaymentRequest.Status.AUDITED:
        recipients = _unique_users(
            _users_with_perm('payments.can_final_approve'),
            _admin_users(),
            exclude=actor,
        )
        _create_notifications(
            recipients,
            title='طلب دفع بانتظار الاعتماد النهائي',
            message=f'تم تدقيق طلب الدفع #{payment.pk} وهو بانتظار الاعتماد النهائي.',
            link=link,
        )
        return

    if new_status == PaymentRequest.Status.FINAL_APPROVED:
        recipients = _unique_users([payment.created_by], _admin_users(), exclude=actor)
        _create_notifications(
            recipients,
            title='تم اعتماد طلب الدفع نهائياً',
            message=f'تم اعتماد طلب الدفع #{payment.pk} نهائياً بواسطة {actor_name}.',
            link=link,
        )
        return

    if new_status == PaymentRequest.Status.REJECTED:
        recipients = _unique_users([payment.created_by], _admin_users(), exclude=actor)
        reason = payment.rejection_reason.strip()
        message = f'تم رفض طلب الدفع #{payment.pk} بواسطة {actor_name}.'
        if reason:
            message += f' السبب: {reason}'
        _create_notifications(
            recipients,
            title='تم رفض طلب الدفع',
            message=message,
            link=link,
        )
        return

    recipients = _unique_users(_admin_users(), exclude=actor)
    _create_notifications(
        recipients,
        title='تحديث على طلب دفع',
        message=f'تغيرت حالة طلب الدفع #{payment.pk} إلى {status_label}.',
        link=link,
    )


def mark_notification_read(notification, user):
    if notification.recipient_id != user.pk or notification.is_read:
        return False
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=['is_read', 'read_at'])
    return True


def mark_all_notifications_read(user):
    return Notification.objects.filter(recipient=user, is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )
