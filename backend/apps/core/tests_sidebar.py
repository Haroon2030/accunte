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
WORK_ALL = {'inbox', 'requests', 'cases', 'proposals', 'suppliers'}

EXPECTED = {
    RT.ADMIN: EXECUTIVE | WORK_ALL | {'distribution', 'service_types', 'branches', 'users', 'roles', 'audit', 'whatsapp_link'},
    RT.CFO: EXECUTIVE | WORK_ALL | {'distribution', 'service_types', 'branches', 'audit', 'whatsapp_link'},
    RT.MANAGER: EXECUTIVE | WORK_ALL | {'distribution', 'service_types', 'branches', 'audit', 'whatsapp_link'},
    RT.AUDITOR: EXECUTIVE | WORK_ALL | {'audit'},
    RT.CS_SUPERVISOR: {'inbox', 'requests', 'cases', 'distribution', 'proposals', 'suppliers', 'whatsapp_link'},
    RT.CS_AGENT: {'inbox', 'requests', 'cases', 'suppliers'},
    RT.ACCOUNTANT: {'requests', 'cases', 'proposals', 'suppliers'},
    RT.PAYMENT_OFFICER: {'proposals', 'suppliers'},
    RT.BRANCH_EMPLOYEE: set(),
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

    def test_users_and_roles_pages_are_admin_only(self):
        for role in (RT.CFO, RT.MANAGER, RT.AUDITOR, RT.CS_SUPERVISOR):
            self.assertFalse({'users', 'roles'} & keys_for(make_user(f'x_{role}', role)), role)

    def test_every_nav_url_resolves_and_keys_are_unique(self):
        keys = [i.key for _, items in sidebar.SECTIONS for i in items]
        self.assertEqual(len(keys), len(set(keys)))
        for _, items in sidebar.SECTIONS:
            for item in items:
                self.assertTrue(reverse(item.url_name).startswith('/'), item.key)

    def test_accountant_cases_item_is_called_my_tasks(self):
        req = RequestFactory().get('/')
        req.user = make_user('acc', RT.ACCOUNTANT)
        labels = {i['key']: i['label'] for i in sidebar.leaves(sidebar.build(req))}
        self.assertEqual(labels['cases'], 'مهامي')
        req.user = make_user('cfo', RT.CFO)
        labels = {i['key']: i['label'] for i in sidebar.leaves(sidebar.build(req))}
        self.assertEqual(labels['cases'], 'حالات المطابقة')


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
            '/reconciliation/': ['cases'],
            '/reconciliation/12/': ['cases'],
            '/reconciliation/distribution/': ['distribution'],
            '/service-requests/': ['requests'],
            '/service-requests/5/': ['requests'],
            '/service-requests/types/': ['service_types'],
            '/service-requests/types/2/': ['service_types'],
            '/inbox/3/': ['inbox'],
            '/proposals/create/': ['proposals'],
            '/suppliers/import/': ['suppliers'],
            '/whatsapp/': ['whatsapp_link'],
            '/audit/': ['audit'],
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
        self.assertIn('data-badge="inbox"', html)
        self.assertIn('/static/js/live-nav.js', html)
        self.assertNotIn('لوحة التحكم', html)
        self.assertEqual(html.count('title="لوحة المدير المالي"'), 1)

    def test_anonymous_pages_have_no_sidebar_context(self):
        resp = self.client.get(reverse('auth:login'))
        self.assertNotIn('sidebar_sections', resp.context or {})

    def test_user_card_shows_role_and_initial(self):
        self.client.force_login(make_user('acc', RT.ACCOUNTANT))
        html = self.client.get(reverse('reconciliation:list')).content.decode()
        self.assertIn('class="sb-avatar">A<', html)

    def test_initial_badge_matches_live_endpoint(self):
        SupplierConversation.objects.create(contact_number='966500000001', status='new', unread_count=3,
                                            last_message_at=timezone.now())
        cfo = make_user('cfo', RT.CFO)
        self.client.force_login(cfo)
        html = self.client.get(reverse('reconciliation:executive')).content.decode()
        self.assertIn('data-badge="inbox">1<', html)
        data = self.client.get(reverse('live_badges')).json()
        self.assertEqual(data['badges']['inbox']['count'], 1)


class BadgeCountTests(TestCase):
    def setUp(self):
        self.cfo = make_user('cfo', RT.CFO)
        self.mgr = make_user('mgr', RT.MANAGER)
        self.acc = make_user('acc', RT.ACCOUNTANT)
        self.acc2 = make_user('acc2', RT.ACCOUNTANT)
        self.sup = make_user('sup', RT.CS_SUPERVISOR)
        self.agent = make_user('agent', RT.CS_AGENT)
        self.po = make_user('po', RT.PAYMENT_OFFICER)
        self.aud = make_user('aud', RT.AUDITOR)
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
        return ServiceRequest.objects.create(service_type=t, supplier=self.supplier, subject='x', created_by=self.agent,
                                             due_at=kw.pop('due_at', timezone.now() + datetime.timedelta(hours=5)), **kw)

    def proposal(self, status, amount=1000, creator=None):
        c = self.case(status='completed')
        return PaymentProposal.objects.create(
            supplier=self.supplier, branch=self.branch, reconciliation_case=c, total_dues=amount * 2,
            proposed_amount=amount, justification='x', created_by=creator or self.acc, status=status,
            requires_cfo=amount >= 50000)

    def test_no_badges_when_nothing_pending(self):
        for u in (self.cfo, self.acc, self.sup, self.po):
            self.assertEqual(self.counts(u), {}, u.username)

    def test_inbox_counts_unread_conversations_and_turns_red_when_late(self):
        SLAConfiguration.objects.update_or_create(name='default', defaults={'first_response_minutes': 30})
        SupplierConversation.objects.create(contact_number='966500000001', unread_count=2, status='new')
        SupplierConversation.objects.create(contact_number='966500000002', unread_count=0, status='open')       # مقروءة
        SupplierConversation.objects.create(contact_number='966500000003', unread_count=1, status='closed')     # مغلقة
        self.assertEqual(self.counts(self.sup)['inbox'], {'count': 1, 'tone': 'info'})
        SupplierConversation.objects.create(contact_number='966500000004', unread_count=1, status='open',
                                            awaiting_reply_since=timezone.now() - datetime.timedelta(hours=2))
        self.assertEqual(self.counts(self.sup)['inbox'], {'count': 2, 'tone': 'danger'})

    def test_requests_mine_plus_unassigned_and_overdue_tone(self):
        self.request(assigned_to=self.acc)
        self.request()                                                 # غير مسند ويخص المحاسبين
        self.request(assigned_to=self.acc2)                            # لزميله: لا يُحسب
        self.request(assigned_to=self.acc, status='closed')            # منتهٍ
        self.assertEqual(self.counts(self.acc)['requests'], {'count': 2, 'tone': 'info'})
        self.request(assigned_to=self.acc, due_at=timezone.now() - datetime.timedelta(hours=1))
        self.assertEqual(self.counts(self.acc)['requests'], {'count': 3, 'tone': 'danger'})

    def test_requests_for_cfo_and_auditor_count_only_overdue(self):
        self.request(assigned_to=self.acc)
        self.assertNotIn('requests', self.counts(self.cfo))
        self.request(due_at=timezone.now() - datetime.timedelta(hours=1))
        self.assertEqual(self.counts(self.cfo)['requests'], {'count': 1, 'tone': 'danger'})
        self.assertEqual(self.counts(self.aud)['requests'], {'count': 1, 'tone': 'danger'})

    def test_cases_badge_by_role(self):
        self.case(accountant=self.acc)
        self.case(accountant=self.acc2)
        self.case(status='completed', accountant=self.acc)
        self.assertEqual(self.counts(self.acc)['cases'], {'count': 1, 'tone': 'info'})
        self.assertNotIn('cases', self.counts(self.cfo))                  # لا متأخر
        self.case(accountant=self.acc, due=self.today - datetime.timedelta(days=1))
        self.assertEqual(self.counts(self.acc)['cases'], {'count': 2, 'tone': 'danger'})
        self.assertEqual(self.counts(self.cfo)['cases'], {'count': 1, 'tone': 'danger'})
        self.assertNotIn('cases', self.counts(self.agent))

    def test_distribution_counts_ready_cases(self):
        self.case(status='ready_for_distribution')
        self.case(status='ready_for_distribution')
        self.case()
        self.assertEqual(self.counts(self.sup)['distribution'], {'count': 2, 'tone': 'warn'})
        self.assertNotIn('distribution', self.counts(self.acc))                # غير ظاهر لها

    def test_proposals_badge_by_role(self):
        self.proposal('pending_review', 80000)                            # يخص المدير المالي
        self.proposal('submitted', 5000)                                  # يخص المدير
        self.proposal('approved')                                         # بانتظار الصرف
        self.proposal('needs_info', creator=self.acc)
        self.assertEqual(self.counts(self.cfo)['proposals']['count'], 1)
        self.assertEqual(self.counts(self.mgr)['proposals']['count'], 1)
        self.assertEqual(self.counts(self.po)['proposals']['count'], 1)
        self.assertEqual(self.counts(self.acc)['proposals']['count'], 1)       # استيضاح على مقترحه
        self.assertNotIn('proposals', self.counts(self.aud))
        admin = make_user('adm', RT.ADMIN)
        self.assertEqual(self.counts(admin)['proposals']['count'], 2)

    def test_only_visible_items_are_computed(self):
        self.case(status='ready_for_distribution')
        self.assertEqual(live.badge_counts(self.acc, ['distribution']), {'distribution': {'count': 1, 'tone': 'warn'}})
        self.assertEqual(live.badge_counts(self.acc, ['users', 'audit']), {})


class LiveBadgesEndpointTests(TestCase):
    def test_requires_login_and_is_never_cached(self):
        self.assertEqual(self.client.get(reverse('live_badges')).status_code, 302)
        self.client.force_login(make_user('cfo', RT.CFO))
        r = self.client.get(reverse('live_badges'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Cache-Control'], 'no-store')
        self.assertEqual(set(r.json()), {'badges', 'inbox_latest'})

    def test_latest_inbound_only_for_inbox_roles(self):
        conv = SupplierConversation.objects.create(contact_number='966500000001', display_name='الأفق', status='new')
        ConversationMessage.objects.create(conversation=conv, direction='in', wa_message_id='M1', body='مرحبا بكم')
        ConversationMessage.objects.create(conversation=conv, direction='out', wa_message_id='M2', body='أهلا')
        self.client.force_login(make_user('sup', RT.CS_SUPERVISOR))
        latest = self.client.get(reverse('live_badges')).json()['inbox_latest']
        self.assertEqual((latest['name'], latest['preview'], latest['url']), ('الأفق', 'مرحبا بكم', f'/inbox/{conv.pk}/'))
        self.assertEqual(latest['id'], ConversationMessage.objects.get(wa_message_id='M1').pk)   # الصادرة لا تُعدّ
        self.client.force_login(make_user('acc', RT.ACCOUNTANT))
        self.assertIsNone(self.client.get(reverse('live_badges')).json()['inbox_latest'])

    def test_media_message_preview_uses_kind(self):
        conv = SupplierConversation.objects.create(contact_number='966500000001', status='new')
        ConversationMessage.objects.create(conversation=conv, direction='in', wa_message_id='D1', kind='document', body='')
        self.client.force_login(make_user('sup', RT.CS_SUPERVISOR))
        latest = self.client.get(reverse('live_badges')).json()['inbox_latest']
        self.assertEqual(latest['preview'], '[مستند]')
        self.assertEqual(latest['name'], '+966500000001')
