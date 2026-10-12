import re
import secrets

from django.contrib.auth import get_user_model

from .api import ApiError
from .models import UserProfile

User = get_user_model()
USERNAME_RE = re.compile(r'^[a-z0-9._-]{3,30}$')
ROLES = {r for r, _ in UserProfile.Role.choices}


def normalize_username(value):
    """حروف لاتينية صغيرة بلا مسافات؛ تُحوَّل الأرقام العربية إلى لاتينية."""
    table = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
    return str(value or '').translate(table).strip().lower()


def password_error(pw):
    if not pw or len(pw) < 8:
        return 'كلمة المرور 8 خانات على الأقل.'
    if not re.search(r'[A-Za-z]', pw) or not re.search(r'\d', pw):
        return 'يجب أن تحتوي حروفاً إنجليزية وأرقاماً.'
    return ''


def generate_password():
    sets = ['abcdefghjkmnpqrstuvwxyz', 'ABCDEFGHJKMNPQRSTUVWXYZ', '23456789', '@#$%']
    pool = ''.join(sets)
    out = [secrets.choice(s) for s in sets]
    while len(out) < 11:
        out.append(secrets.choice(pool))
    secrets.SystemRandom().shuffle(out)
    return ''.join(out)


def serialize_user(user):
    profile = user.profile
    return {
        'id': user.pk, 'name': user.first_name or user.get_username(), 'username': user.get_username(),
        'role': profile.role, 'org': profile.org, 'active': user.is_active, 'mustChange': profile.must_change_password,
        'last': user.last_login.isoformat() if user.last_login else None,
        'created': user.date_joined.isoformat(),
    }


def validate_user_fields(data, *, user=None, actor=None):
    """يتحقق من حقول إنشاء/تعديل مستخدم ويعيد قاموساً منظفاً. يرفع ApiError عند الخطأ."""
    name = str(data.get('name') or '').strip()
    username = normalize_username(data.get('username'))
    role = str(data.get('role') or '')
    org = str(data.get('org') or '').strip()
    if not name:
        raise ApiError('أدخل الاسم الكامل.')
    if not USERNAME_RE.match(username):
        raise ApiError('اسم المستخدم من 3 إلى 30 خانة: حروف إنجليزية صغيرة وأرقام و . _ - فقط.')
    clash = User.objects.filter(username=username)
    if user is not None:
        clash = clash.exclude(pk=user.pk)
    if clash.exists():
        raise ApiError('اسم المستخدم مستخدم لحساب آخر.')
    if role not in ROLES:
        raise ApiError('دور غير معروف.')
    if role == UserProfile.Role.SUPPLIER and not org:
        raise ApiError('أدخل اسم المورد التابع له الحساب.')
    if user is not None and actor is not None and user.pk == actor.pk and role != user.profile.role:
        raise ApiError('لا يمكنك تغيير دور حسابك الحالي.')
    if role != UserProfile.Role.SUPPLIER and not org:
        org = 'أسواق الراشد'
    return {'name': name[:150], 'username': username, 'role': role, 'org': org[:150]}
