"""مطابق كشوفات الحساب: الصفحة والصلاحيات وملفات الواجهة، وتشغيل اختبارات المحرّك (Node) إن توفّر."""
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Role, UserProfile
from apps.suppliers.models import Supplier

from .statement_views import SCRIPTS

User = get_user_model()
RT = Role.RoleType


def make_user(username, role_type, supplier=None):
    role, _ = Role.objects.get_or_create(role_type=role_type, defaults={'name': f'r-{role_type}', 'is_system_role': True})
    u = User.objects.create_user(username, password='x-Pass-12345')
    UserProfile.objects.create(user=u, role=role, supplier=supplier)
    return u


class StatementPageTests(TestCase):
    url = '/statement-matcher/'

    def test_allowed_roles_see_the_page(self):
        for role in (RT.ADMIN, RT.CFO, RT.ACCOUNTANT, RT.CS_SUPERVISOR):
            self.client.force_login(make_user(f'u_{role}', role))
            resp = self.client.get(self.url)
            self.assertEqual(resp.status_code, 200, role)
            self.assertContains(resp, 'id="sm-root"')
            self.assertContains(resp, 'مطابق كشوفات الحساب')

    def test_supplier_account_and_anonymous_are_kept_out(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        vendor = make_user('vendor', RT.SUPPLIER, Supplier.objects.create(name='م', code='M1'))
        self.client.force_login(vendor)
        resp = self.client.get(self.url)
        self.assertEqual((resp.status_code, resp['Location']), (302, '/portal/'))

    def test_page_is_read_only_and_receives_no_data(self):
        self.client.force_login(make_user('acc', RT.ACCOUNTANT))
        self.assertEqual(self.client.post(self.url, {'x': 1}).status_code, 405)

    def test_all_scripts_and_css_are_served_with_version(self):
        self.client.force_login(make_user('acc', RT.ACCOUNTANT))
        html = self.client.get(self.url).content.decode()
        for name in SCRIPTS:
            self.assertIn(f'statement/{name}?v=', html, name)
            self.assertIsNotNone(finders.find(f'statement/{name}'), name)
        self.assertIn('statement/statement.css?v=', html)
        self.assertIsNotNone(finders.find('statement/statement.css'))

    def test_script_order_respects_dependencies(self):
        order = list(SCRIPTS)
        for earlier, later in (('sm-core.js', 'sm-xlsx.js'), ('sm-xlsx.js', 'sm-ledger.js'), ('sm-ledger.js', 'sm-engine.js'),
                               ('sm-engine.js', 'sm-report.js'), ('sm-table.js', 'sm-readers.js'), ('sm-readers.js', 'sm-app.js')):
            self.assertLess(order.index(earlier), order.index(later), (earlier, later))

    def test_sidebar_lists_the_section_for_reconcilers(self):
        self.client.force_login(make_user('acc', RT.ACCOUNTANT))
        html = self.client.get(reverse('reconciliation:list')).content.decode()
        self.assertIn('data-nav="statement"', html)


class EngineJsTests(TestCase):
    """يشغّل اختبارات المحرّك الحسابي (قراءة الأرقام والتواريخ، الدفاتر، المطابقة، التقارير، Excel) عبر Node."""

    def test_node_suite_passes(self):
        node = shutil.which('node')
        tests = Path(settings.BASE_DIR) / 'static' / 'statement' / 'tests'
        if node is None or not tests.exists():
            self.skipTest('Node.js غير متاح في هذه البيئة')
        files = sorted(str(p) for p in tests.glob('*.test.js'))
        proc = subprocess.run([node, '--test', *files], capture_output=True, text=True, encoding='utf-8', timeout=180)
        self.assertEqual(proc.returncode, 0, (proc.stdout or '')[-3000:] + (proc.stderr or '')[-1500:])
