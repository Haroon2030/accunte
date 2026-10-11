"""
الشريط الجانبي: مصدر واحد للأقسام والعناصر والأدوار، وتفعيل العنصر الحالي، والعدّادات الحية.

كل عنصر يظهر فقط للأدوار المسموح لها (مدير النظام يرى الكل). العدّادات تُحسب في apps.core.live
وتُحدَّث من المتصفح كل بضع ثوانٍ دون إعادة تحميل الصفحة.
"""
from dataclasses import dataclass, field

from django.urls import reverse

from apps.core.access import get_role_type, has_role, is_full_admin
from apps.core.models import Role

RT = Role.RoleType

CS = (RT.CS_SUPERVISOR,)
OVERSIGHT = (RT.CFO,)


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
    group: str = ''                # مفتاح المجموعة القابلة للطي التي يندرج تحتها (فارغ = عنصر مستقل)


# عنوان رئيسي تحته شاشات فرعية: مفتاح المجموعة ← (التسمية، الأيقونة)
GROUPS = {
    'setup': ('تهيئة النظام', 'settings-2'),
    'access': ('المستخدمون والصلاحيات', 'key-round'),
}


SECTIONS = (
    ('نظرة عامة', (
        NavItem('executive', 'لوحة المدير المالي', 'layout-dashboard', 'reconciliation:executive',
                ('/reconciliation/executive/',), OVERSIGHT),
    )),
    ('العمليات', (
        NavItem('requests', 'استلام الطلبات', 'inbox', 'servicedesk:list', ('/service-requests/',),
                OVERSIGHT + CS, exclude=('/service-requests/types', '/service-requests/my-tasks')),
        NavItem('my_tasks', 'مهامي', 'list-checks', 'servicedesk:my_tasks', ('/service-requests/my-tasks',),
                (RT.ACCOUNTANT,)),
        NavItem('statement', 'مطابقة كشوف الحساب', 'file-spreadsheet', 'statement_matcher', ('/statement-matcher/',),
                (RT.CFO, RT.CS_SUPERVISOR, RT.ACCOUNTANT)),
        NavItem('proposals', 'أوامر الدفع المقترحة', 'file-check-2', 'proposals:list', ('/proposals/',),
                OVERSIGHT + (RT.CS_SUPERVISOR, RT.ACCOUNTANT)),
    )),
    ('البيانات الرئيسية', (
        NavItem('suppliers', 'حسابات الموردين', 'contact', 'suppliers:list', ('/suppliers/',),
                OVERSIGHT + CS + (RT.ACCOUNTANT,)),
        NavItem('service_types', 'تصنيفات الخدمة', 'tags', 'servicedesk:types',
                ('/service-requests/types',), (RT.CFO,), group='setup'),
        NavItem('branches', 'الفروع ومراكز التكلفة', 'building-2', 'branches:list', ('/branches/',), (RT.CFO,), group='setup'),
    )),
    ('الحوكمة والامتثال', (
        NavItem('users', 'المستخدمون', 'users', 'users:list', ('/users/',), (), group='access'),
        NavItem('roles', 'الأدوار والصلاحيات', 'shield-check', 'roles:list', ('/roles/',), (), group='access'),
        NavItem('whatsapp_link', 'تكامل واتساب', 'plug-zap', 'whatsapp:connect', ('/whatsapp/',),
                (RT.CFO, RT.CS_SUPERVISOR)),
    )),
)

# عناصر قسم «النظام» الإدارية لا يراها إلا مدير النظام ما لم تُحدَّد أدوار صراحةً
ADMIN_ONLY = {'users', 'roles'}


def _allowed(user, item):
    if item.key in ADMIN_ONLY:
        return is_full_admin(user)
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


def _fold_groups(rows):
    """يجمع العناصر ذات المجموعة المشتركة تحت عنوان واحد (في موضع أول عنصر منها)."""
    entries, groups = [], {}
    for row in rows:
        key = row.pop('group')
        if not key:
            entries.append(row)
            continue
        if key not in groups:
            label, icon = GROUPS[key]
            groups[key] = {'group': True, 'key': key, 'label': label, 'icon': icon, 'items': []}
            entries.append(groups[key])
        groups[key]['items'].append(row)
    for g in groups.values():
        g['active'] = any(i['active'] for i in g['items'])
        g['badge_count'] = sum(i['badge_count'] for i in g['items'])
        g['badge_tone'] = 'danger' if any(i['badge_tone'] == 'danger' for i in g['items'] if i['badge_count']) else 'info'
    return entries


def leaves(sections):
    """كل العناصر الورقية (بعد فكّ المجموعات) بترتيبها."""
    return [leaf for s in sections for e in s['entries'] for leaf in (e['items'] if e.get('group') else [e])]


def build(request, counts=None):
    """هيكل جاهز للقالب: أقسام فيها مدخلات؛ المدخل عنصر مستقل أو مجموعة فيها عناصر فرعية."""
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
                'group': item.group,
            })
        if rows:
            sections.append({'title': title, 'entries': _fold_groups(rows)})
    return sections


def context_processor(request):
    """يضيف sidebar_sections إلى كل قالب (للمستخدمين المسجّلين فقط)."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    from apps.core.live import badge_counts
    return {'sidebar_sections': build(request, badge_counts(user, visible_keys(user)))}
