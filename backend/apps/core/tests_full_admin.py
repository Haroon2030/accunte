"""المدير المالي يملك صلاحيات سوبر أدمن: كل فحوص الأدوار وإدارة المستخدمين والصلاحيات."""
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.core import sidebar
from apps.core.access import has_role, is_full_admin
from apps.core.models import Role, UserProfile

RT = Role.RoleType


def make_user(username, role_type):
    user = get_user_model().objects.create_user(username, password='x')
    role, _ = Role.objects.get_or_create(role_type=role_type, defaults={'name': role_type})
    UserProfile.objects.update_or_create(user=user, defaults={'role': role})
    return user


class CfoFullAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cfo = make_user('fa_cfo', RT.CFO)
        cls.acc = make_user('fa_acc', RT.ACCOUNTANT)

    def test_helpers(self):
        self.assertTrue(is_full_admin(self.cfo))
        self.assertFalse(is_full_admin(self.acc))
        self.assertTrue(has_role(self.cfo, RT.SUPPLIER))     # يتجاوز أي دور مطلوب
        self.assertFalse(has_role(self.acc, RT.SUPPLIER))

    def test_cfo_reaches_user_and_role_management(self):
        self.client.force_login(self.cfo)
        for url in ('/users/', '/roles/'):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.client.force_login(self.acc)
        for url in ('/users/', '/roles/'):
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_cfo_sees_admin_sidebar_items(self):
        req = RequestFactory().get('/')
        req.user = self.cfo
        keys = {i['key'] for i in sidebar.leaves(sidebar.build(req))}
        self.assertTrue({'users', 'roles'} <= keys)
