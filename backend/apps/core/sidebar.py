"""
الشريط الجانبي: مصدر واحد للأقسام والعناصر والأدوار، وتفعيل العنصر الحالي، والعدّادات الحية.

كل عنصر يظهر فقط للأدوار المسموح لها (مدير النظام يرى الكل). العدّادات تُحسب في apps.core.live
وتُحدَّث من المتصفح كل بضع ثوانٍ دون إعادة تحميل الصفحة.
"""
from dataclasses import dataclass, field

from django.urls import reverse

from apps.core.access import get_role_type, has_role
from apps.core.models import Role

RT = Role.RoleType

CS = (RT.CS_SUPERVISOR, RT.CS_AGENT)
OVERSIGHT = (RT.CFO, RT.MANAGER, RT.AUDITOR)


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str
    url_name: str
    prefixes: tuple
    roles: tuple = ()              # فارغ = كل الأدوار
    exclude: tuple = ()            # مسارات تحت البادئة لها عنصر خاص بها
    label_by_role: dict = field(default_factory=dict)


SECTIONS = (
    ('', (
        NavItem('executive', 'لوحة المدير المالي', 'layout-dashboard', 'reconciliation:executive',
                ('/reconciliation/executive/',), OVERSIGHT),
    )),
    ('العمل اليومي', (
        NavItem('inbox', 'صندوق واتساب', 'message-circle', 'whatsapp_inbox:inbox', ('/inbox/',), OVERSIGHT + CS),
        NavItem('requests', 'طلبات الخدمة', 'clipboard-list', 'servicedesk:list', ('/service-requests/',),
                OVERSIGHT + CS + (RT.ACCOUNTANT,), exclude=('/service-requests/types',)),
        NavItem('cases', 'حالات المطابقة', 'scale', 'reconciliation:list', ('/reconciliation/',),
                OVERSIGHT + CS + (RT.ACCOUNTANT,),
                exclude=('/reconciliation/executive', '/reconciliation/distribution'),
                label_by_role={RT.ACCOUNTANT: 'مهامي'}),
        NavItem('distribution', 'توزيع الملفات', 'split', 'reconciliation:distribution',
                ('/reconciliation/distribution/',), (RT.CFO, RT.MANAGER, RT.CS_SUPERVISOR)),
        NavItem('proposals', 'مقترحات الدفع', 'file-check-2', 'proposals:list', ('/proposals/',),
                OVERSIGHT + (RT.CS_SUPERVISOR, RT.ACCOUNTANT, RT.PAYMENT_OFFICER)),
    )),
    ('الإدارة', (
        NavItem('suppliers', 'الموردين', 'briefcase', 'suppliers:list', ('/suppliers/',),
                OVERSIGHT + CS + (RT.ACCOUNTANT, RT.PAYMENT_OFFICER)),
        NavItem('service_types', 'أنواع الخدمات', 'sliders-horizontal', 'servicedesk:types',
                ('/service-requests/types',), (RT.CFO, RT.MANAGER)),
        NavItem('branches', 'الفروع', 'building-2', 'branches:list', ('/branches/',), (RT.CFO, RT.MANAGER)),
    )),
    ('النظام', (
        NavItem('users', 'المستخدمين', 'users', 'users:list', ('/users/',), ()),
        NavItem('roles', 'الأدوار', 'shield-check', 'roles:list', ('/roles/',), ()),
        NavItem('audit', 'سجل التدقيق', 'history', 'audit:list', ('/audit/',), OVERSIGHT),
        NavItem('whatsapp_link', 'ربط واتساب', 'plug', 'whatsapp:connect', ('/whatsapp/',),
                (RT.CFO, RT.MANAGER, RT.CS_SUPERVISOR)),
    )),
)

# عناصر قسم «النظام» الإدارية لا يراها إلا مدير النظام ما لم تُحدَّد أدوار صراحةً
ADMIN_ONLY = {'users', 'roles'}


def _allowed(user, item):
    if item.key in ADMIN_ONLY:
        return user.is_superuser or get_role_type(user) == RT.ADMIN
    if not item.roles:
        return True
    return has_role(user, *item.roles)


def _is_active(path, item):
    if any(path.startswith(x) for x in item.exclude):
        return False
    return any(path.startswith(p) for p in item.prefixes)


def visible_items(user):
    """[(قسم, عنصر)] التي يحق لهذا المستخدم رؤيتها."""
    return [(title, item) for title, items in SECTIONS for item in items if _allowed(user, item)]


def visible_keys(user):
    return [item.key for _, item in visible_items(user)]


def build(request, counts=None):
    """هيكل جاهز للقالب: أقسام فيها عناصر (label, icon, url, active, badge)."""
    user = request.user
    role = get_role_type(user)
    sections = []
    for title, items in SECTIONS:
        rows = []
        for item in items:
            if not _allowed(user, item):
                continue
            badge = (counts or {}).get(item.key)
            rows.append({
                'key': item.key,
                'label': item.label_by_role.get(role, item.label),
                'icon': item.icon,
                'url': reverse(item.url_name),
                'active': _is_active(request.path, item),
                'badge_count': badge['count'] if badge else 0,
                'badge_tone': badge['tone'] if badge else 'info',
            })
        if rows:
            sections.append({'title': title, 'items': rows})
    return sections


def context_processor(request):
    """يضيف sidebar_sections إلى كل قالب (للمستخدمين المسجّلين فقط)."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    from apps.core.live import badge_counts
    return {'sidebar_sections': build(request, badge_counts(user, visible_keys(user)))}
