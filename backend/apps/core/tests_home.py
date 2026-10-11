"""
الصفحة الرئيسية `/`: بعد حذف لوحة التحكم القديمة صارت توجيهًا حسب الدور.
الخطر: صفحة هبوط ترفض الدور فتحوّله إلى `/` من جديد (حلقة لانهائية). نتحقق أن لكل دور تحويلًا واحدًا إلى صفحة تقبله.
"""
from django.contrib.auth import get_user_model
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.test import TestCase

from apps.core.models import Role, UserProfile
from apps.suppliers.models import Supplier
from apps.core.web_views import DEFAULT_HOME, HOME_BY_ROLE

User = get_user_model()
RT = Role.RoleType

EXPECTED_PATH = {
    RT.ADMIN: '/reconciliation/executive/',
    RT.CFO: '/reconciliation/executive/',
    RT.ACCOUNTANT: '/service-requests/my-tasks/',
    RT.CS_SUPERVISOR: '/service-requests/',
    RT.SUPPLIER: '/portal/',
}


def make_user(username, role_type=None):
    u = User.objects.create_user(username, password='x-Pass-12345')
    if role_type is not None:
        role, _ = Role.objects.get_or_create(role_type=role_type, defaults={'name': f'r-{role_type}', 'is_system_role': True})
        UserProfile.objects.create(user=u, role=role)
    return u


class HomeRedirectTests(TestCase):
    def test_every_role_lands_on_a_page_that_accepts_it_with_one_hop(self):
        for role, path in EXPECTED_PATH.items():
            user = make_user(f'u_{role}', role)
            if role == RT.SUPPLIER:
                user.profile.supplier = Supplier.objects.create(name='مورد', code='HS1')
                user.profile.save()
            self.client.force_login(user)
            resp = self.client.get('/', follow=True)
            self.assertEqual(len(resp.redirect_chain), 1, f'{role}: {resp.redirect_chain}')   # لا حلقة ولا قفزات
            self.assertEqual(resp.redirect_chain[0][0], path, role)
            self.assertEqual(resp.status_code, 200, role)

    def test_all_roles_are_covered(self):
        self.assertEqual(set(EXPECTED_PATH), set(Role.RoleType.values))
        for role in HOME_BY_ROLE:
            self.assertIn(role, EXPECTED_PATH)

    def test_user_without_role_and_superuser(self):
        self.client.force_login(make_user('norole'))
        resp = self.client.get('/', follow=True)
        self.assertEqual((len(resp.redirect_chain), resp.status_code), (1, 200))
        self.assertTrue(resp.redirect_chain[0][0].endswith('/payments/'))
        root = User.objects.create_superuser('root', password='x-Pass-12345')
        self.client.force_login(root)
        resp = self.client.get('/', follow=True)
        self.assertEqual(resp.redirect_chain[0][0], '/reconciliation/executive/')
        self.assertEqual(resp.status_code, 200)

    def test_permission_denied_redirect_does_not_loop(self):
        """رفض الصلاحية يحوّل إلى dashboard، ثم إلى صفحة الدور، وتنتهي السلسلة بـ200."""
        self.client.force_login(make_user('acc', RT.ACCOUNTANT))
        resp = self.client.get('/reconciliation/executive/', follow=True)     # المحاسب ممنوع منها
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.redirect_chain), 2)
        self.assertEqual(resp.redirect_chain[-1][0], '/service-requests/my-tasks/')

    def test_anonymous_goes_to_login(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login/', resp.url)


class OldDashboardRemovedTests(TestCase):
    def test_template_is_gone(self):
        with self.assertRaises(TemplateDoesNotExist):
            get_template('pages/dashboard.html')

    def test_no_control_panel_link_in_any_role_sidebar(self):
        for role in (RT.CFO, RT.ACCOUNTANT, RT.CS_SUPERVISOR):
            self.client.force_login(make_user(f's_{role}', role))
            html = self.client.get('/', follow=True).content.decode()
            self.assertNotIn('title="لوحة التحكم"', html, role)
            self.assertNotIn('>لوحة التحكم<', html, role)
