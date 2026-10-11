"""
الشريط الجانبي: ظهور العناصر حسب الدور، التفعيل، العدّادات الحية، ونقطة البيانات /live/badges/.
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.branches.models import Branch
from apps.core import live, sidebar
from apps.core.models import Role, UserProfile
from apps.proposals.models import PaymentProposal
from apps.reconciliation.models import ReconciliationCase
from apps.servicedesk.models import ServiceRequest, ServiceType
from apps.suppliers.models import Supplier
from apps.whatsapp.models import ConversationMessage, SLAConfiguration, SupplierConversation

User = get_user_model()
RT = Role.RoleType


def make_user(username, role_type=None):
    u = User.objects.create_user(username, password='x-Pass-12345')
    if role_type is not None:
        role, _ = Role.objects.get_or_create(role_type=role_type, defaults={'name': f'r-{role_type}', 'is_system_role': True})
        UserProfile.objects.create(user=u, role=role)
    return u


def keys_for(user):
    return set(sidebar.visible_keys(user))


EXECUTIVE = {'executive'}
WORK_ALL = {'requests', 'my_tasks', 'proposals', 'suppliers', 'statement'}

EXPECTED = {
    RT.ADMIN: EXECUTIVE | WORK_ALL | {'service_types', 'branches', 'users', 'roles', 'whatsapp_link'},
    RT.CFO: EXECUTIVE | WORK_ALL | {'service_types', 'branches', 'whatsapp_link', 'users', 'roles'},
    RT.CS_SUPERVISOR: {'requests', 'proposals', 'suppliers', 'whatsapp_link', 'statement'},
    RT.ACCOUNTANT: {'my_tasks', 'proposals', 'suppliers', 'statement'},
    RT.SUPPLIER: set(),
}


class VisibilityByRoleTests(TestCase):
    def test_each_role_sees_exactly_its_items(self):
        for role, expected in EXPECTED.items():
            self.assertEqual(keys_for(make_user(f'u_{role}', role)), expected, role)

    def test_every_role_is_covered(self):
        self.assertEqual(set(EXPECTED), set(Role.RoleType.values))

    def test_superuser_without_profile_is_admin(self):
        root = User.objects.create_superuser('root', password='x-Pass-12345')
        self.assertEqual(keys_for(root), EXPECTED[RT.ADMIN])

    def test_user_without_role_sees_nothing(self):
        self.assertEqual(keys_for(make_user('norole')), set())

    def test_users_and_roles_pages_are_for_full_admins_only(self):
        for role in (RT.CS_SUPERVISOR, RT.ACCOUNTANT):  # المدير المالي سوبر أدمن؛ هؤلاء لا
            self.assertFalse({'users', 'roles'} & keys_for(make_user(f'x_{role}', role)), role)

    def test_every_nav_url_resolves_and_keys_are_unique(self):
        keys = [i.key for _, items in sidebar.SECTIONS for i in items]
        self.assertEqual(len(keys), len(set(keys)))
        for _, items in sidebar.SECTIONS:
            for item in items:
                self.assertTrue(reverse(item.url_name).startswith('/'), item.key)


class ActiveItemTests(TestCase):
    """كل مسار يُفعّل عنصرًا واحدًا فقط (لا التباس بين البادئات المتداخلة)."""

    def active(self, path, user):
        req = RequestFactory().get(path)
        req.user = user
        return [i['key'] for i in sidebar.leaves(sidebar.build(req)) if i['active']]

    def test_paths_map_to_one_item(self):
        admin = make_user('adm', RT.ADMIN)
        cases = {
            '/reconciliation/executive/': ['executive'],
            '/reconciliation/executive/print/': ['executive'],
            '/statement-matcher/': ['statement'],
            '/service-requests/types/': ['service_types'],
            '/service-requests/types/2/': ['service_types'],
            '/proposals/create/': ['proposals'],
            '/suppliers/import/': ['suppliers'],
            '/whatsapp/': ['whatsapp_link'],
            '/users/': ['users'],
            '/payments/': [],
        }
        for path, expected in cases.items():
            self.assertEqual(self.active(path, admin), expected, path)


class SidebarRenderingTests(TestCase):
    def test_html_has_items_badges_and_no_old_control_panel(self):
        cfo = make_user('cfo', RT.CFO)
        self.client.force_login(cfo)
        html = self.client.get(reverse('reconciliation:executive')).content.decode()
        self.assertIn('class="sb-link is-active"', html)
        self.assertIn('aria-current="page"', html)
        self.assertIn('/static/js/live-nav.js', html)
        self.assertNotIn('لوحة التحكم', html)
        self.assertEqual(html.count('title="لوحة المدير المالي"'), 1)

    def test_anonymous_pages_have_no_sidebar_context(self):
        resp = self.client.get(reverse('auth:login'))
        self.assertNotIn('sidebar_sections', resp.context or {})

    def test_user_card_shows_role_and_initial(self):
        self.client.force_login(make_user('acc', RT.ACCOUNTANT))
        html = self.client.get(reverse('statement_matcher')).content.decode()
        self.assertIn('class="sb-avatar">A<', html)


class BadgeCountTests(TestCase):
    def setUp(self):
        self.cfo = make_user('cfo', RT.CFO)
        self.acc = make_user('acc', RT.ACCOUNTANT)
        self.acc2 = make_user('acc2', RT.ACCOUNTANT)
        self.sup = make_user('sup', RT.CS_SUPERVISOR)
        self.supplier = Supplier.objects.create(name='مورد', code='S1')
        self.branch = Branch.objects.create(name='ب', code='B')
        self.today = timezone.localdate()

    def counts(self, user):
        return live.badge_counts(user, sidebar.visible_keys(user))

    def case(self, status='reconciling', accountant=None, due=None):
        return ReconciliationCase.objects.create(
            supplier=self.supplier, period_start=datetime.date(2026, 1, 1), period_end=datetime.date(2026, 2, 1),
            created_by=self.sup, status=status, assigned_accountant=accountant, due_date=due)

    def request(self, **kw):
        t = ServiceType.objects.get(code='payment-status')
        return ServiceRequest.objects.create(service_type=t, supplier=self.supplier, subject='x', created_by=self.sup,
                                             due_at=kw.pop('due_at', timezone.now() + datetime.timedelta(hours=5)), **kw)

    def proposal(self, status, amount=1000, creator=None):
        c = self.case(status='completed')
        return PaymentProposal.objects.create(
            supplier=self.supplier, branch=self.branch, reconciliation_case=c, total_dues=amount * 2,
            proposed_amount=amount, justification='x', created_by=creator or self.acc, status=status,
            requires_cfo=amount >= 50000)

    def test_no_badges_when_nothing_pending(self):
        for u in (self.cfo, self.acc, self.sup):
            self.assertEqual(self.counts(u), {}, u.username)


    def test_proposals_badge_by_role(self):
        self.proposal('pending_review', 80000)                            # بانتظار قرار المدير المالي
        self.proposal('submitted', 5000)
        self.proposal('approved')                                         # معتمد بانتظار الصرف
        self.proposal('needs_info', creator=self.acc)
        self.assertEqual(self.counts(self.cfo)['proposals']['count'], 3)
        self.assertEqual(self.counts(self.acc)['proposals']['count'], 1)       # استيضاح على مقترحه
        admin = make_user('adm', RT.ADMIN)
        self.assertEqual(self.counts(admin)['proposals']['count'], 3)
        self.assertNotIn('proposals', self.counts(self.sup))


class LiveBadgesEndpointTests(TestCase):
    def test_requires_login_and_is_never_cached(self):
        self.assertEqual(self.client.get(reverse('live_badges')).status_code, 302)
        self.client.force_login(make_user('cfo', RT.CFO))
        r = self.client.get(reverse('live_badges'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Cache-Control'], 'no-store')
        self.assertEqual(set(r.json()), {'badges'})


