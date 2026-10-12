import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from .models import UserProfile
from .services import password_error

User = get_user_model()
Role = UserProfile.Role


def make_user(username, role, *, org='أسواق الراشد', password='Pass@1234', must_change=False, name=None, active=True):
    u = User.objects.create_user(username, password=password, first_name=name or username, is_active=active)
    UserProfile.objects.create(user=u, role=role, org=org, must_change_password=must_change)
    return u


def post(client, url, data=None, **extra):
    return client.post(url, json.dumps(data or {}), content_type='application/json', **extra)


class PasswordRulesTests(TestCase):
    def test_rules(self):
        self.assertTrue(password_error('short1'))
        self.assertTrue(password_error('onlyletters'))
        self.assertTrue(password_error('12345678'))
        self.assertEqual(password_error('Abcdef12'), '')


class LoginTests(TestCase):
    def setUp(self):
        self.staff = make_user('khaled', Role.MATCHER)
        self.sup = make_user('nokhba', Role.SUPPLIER, org='شركة النخبة')

    def test_staff_login_and_me(self):
        r = post(self.client, '/api/auth/login/', {'username': 'KHALED ', 'password': 'Pass@1234'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['user']['role'], 'matcher')
        me = self.client.get('/api/auth/me/').json()['user']
        self.assertEqual(me['username'], 'khaled')

    def test_portals_are_separated_and_do_not_reveal_accounts(self):
        wrong = post(self.client, '/api/auth/login/', {'username': 'nokhba', 'password': 'Pass@1234'})        # مورد في بوابة الموظفين
        self.assertEqual(wrong.status_code, 401)
        missing = post(self.client, '/api/auth/login/', {'username': 'nobody', 'password': 'x'})
        self.assertEqual(wrong.json()['error'], missing.json()['error'])
        ok = post(self.client, '/api/auth/login/', {'username': 'nokhba', 'password': 'Pass@1234', 'portal': 'supplier'})
        self.assertEqual(ok.status_code, 200)
        self.client.logout()
        staff_in_supplier = post(self.client, '/api/auth/login/', {'username': 'khaled', 'password': 'Pass@1234', 'portal': 'supplier'})
        self.assertEqual(staff_in_supplier.status_code, 401)

    @override_settings(LOGIN_MAX_FAILS=3, LOGIN_LOCK_SECONDS=60)
    def test_lockout_after_failures(self):
        for _ in range(2):
            self.assertEqual(post(self.client, '/api/auth/login/', {'username': 'khaled', 'password': 'bad'}).status_code, 401)
        locked = post(self.client, '/api/auth/login/', {'username': 'khaled', 'password': 'bad'})
        self.assertEqual(locked.status_code, 429)
        again = post(self.client, '/api/auth/login/', {'username': 'khaled', 'password': 'Pass@1234'})   # حتى الصحيحة مرفوضة أثناء القفل
        self.assertEqual(again.status_code, 429)
        self.assertGreater(again.json()['retryAfter'], 0)

    def test_inactive_account_is_refused_after_correct_password(self):
        make_user('off', Role.MATCHER, active=False)
        r = post(self.client, '/api/auth/login/', {'username': 'off', 'password': 'Pass@1234'})
        self.assertEqual(r.status_code, 403)

    def test_logout_and_protected_endpoints(self):
        self.assertEqual(self.client.get('/api/bootstrap/').status_code, 401)
        post(self.client, '/api/auth/login/', {'username': 'khaled', 'password': 'Pass@1234'})
        self.assertEqual(self.client.get('/api/bootstrap/').status_code, 200)
        post(self.client, '/api/auth/logout/')
        self.assertEqual(self.client.get('/api/bootstrap/').status_code, 401)

    def test_csrf_is_enforced_on_posts(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post('/api/auth/login/', json.dumps({'username': 'khaled', 'password': 'Pass@1234'}), content_type='application/json')
        self.assertEqual(r.status_code, 403)
        c.get('/')                                           # الصفحة تضع كوكي CSRF
        token = c.cookies['csrftoken'].value
        r = c.post('/api/auth/login/', json.dumps({'username': 'khaled', 'password': 'Pass@1234'}),
                   content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200)


class ForcedPasswordChangeTests(TestCase):
    def setUp(self):
        make_user('newbie', Role.MATCHER, password='Temp@1234', must_change=True)

    def test_must_change_blocks_data_until_changed(self):
        post(self.client, '/api/auth/login/', {'username': 'newbie', 'password': 'Temp@1234'})
        blocked = self.client.get('/api/bootstrap/')
        self.assertEqual((blocked.status_code, blocked.json()['code']), (403, 'must_change_password'))
        weak = post(self.client, '/api/auth/change-password/', {'oldPassword': 'Temp@1234', 'newPassword': 'abc'})
        self.assertEqual(weak.status_code, 400)
        same = post(self.client, '/api/auth/change-password/', {'oldPassword': 'Temp@1234', 'newPassword': 'Temp@1234'})
        self.assertEqual(same.status_code, 400)
        ok = post(self.client, '/api/auth/change-password/', {'oldPassword': 'Temp@1234', 'newPassword': 'Fresh@5678'})
        self.assertEqual(ok.status_code, 200)
        self.assertFalse(ok.json()['user']['mustChange'])
        self.assertEqual(self.client.get('/api/bootstrap/').status_code, 200)          # الجلسة بقيت صالحة


class UserAdminTests(TestCase):
    def setUp(self):
        self.admin = make_user('boss', Role.ADMIN)
        self.matcher = make_user('matcher1', Role.MATCHER)
        self.client.force_login(self.admin)

    def test_only_admin_manages_users(self):
        c = Client()
        c.force_login(self.matcher)
        self.assertEqual(c.get('/api/users/').status_code, 403)
        self.assertEqual(self.client.get('/api/users/').status_code, 200)

    def test_create_validates_and_requires_password_change(self):
        bad = post(self.client, '/api/users/', {'name': 'x', 'username': 'Ab', 'role': 'matcher', 'password': 'Pass@1234'})
        self.assertEqual(bad.status_code, 400)
        no_org = post(self.client, '/api/users/', {'name': 'مورد', 'username': 'sup1', 'role': 'supplier', 'password': 'Pass@1234'})
        self.assertEqual(no_org.status_code, 400)
        ok = post(self.client, '/api/users/', {'name': 'منى', 'username': 'mona', 'role': 'matcher', 'password': 'Match@456'})
        self.assertEqual(ok.status_code, 201)
        self.assertTrue(ok.json()['user']['mustChange'])
        dup = post(self.client, '/api/users/', {'name': 'منى', 'username': 'mona', 'role': 'matcher', 'password': 'Match@456'})
        self.assertEqual(dup.status_code, 400)

    def test_update_toggle_reset_and_self_protection(self):
        r = post(self.client, f'/api/users/{self.matcher.pk}/', {'name': 'خالد', 'username': 'matcher1', 'role': 'manager', 'org': 'الإدارة'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['user']['role'], 'manager')
        self.assertFalse(post(self.client, f'/api/users/{self.matcher.pk}/toggle/').json()['user']['active'])
        self.assertEqual(post(self.client, f'/api/users/{self.admin.pk}/toggle/').status_code, 400)
        self_role = post(self.client, f'/api/users/{self.admin.pk}/', {'name': 'x', 'username': 'boss', 'role': 'matcher'})
        self.assertEqual(self_role.status_code, 400)
        reset = post(self.client, f'/api/users/{self.matcher.pk}/reset-password/').json()
        self.assertEqual(password_error(reset['password']), '')
        self.assertTrue(reset['user']['mustChange'])


class PagesTests(TestCase):
    def test_pages_are_served_with_base_and_csrf_cookie(self):
        for url in ('/', '/portal/', '/supplier/'):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertIn('<base href="/static/frontend/">', r.content.decode())
        self.assertIn('csrftoken', self.client.cookies)
        self.assertEqual(self.client.get('/healthz').status_code, 200)


class BootstrapAdminTests(TestCase):
    def test_existing_superuser_without_profile_becomes_admin_and_can_log_in(self):
        from django.core.management import call_command
        User.objects.create_superuser('1', password='Legacy@1234')           # كحساب الإنتاج القديم: بلا ملف
        self.assertEqual(post(self.client, '/api/auth/login/', {'username': '1', 'password': 'Legacy@1234'}).status_code, 401)
        call_command('bootstrap_admin', stdout=open('NUL' if __import__('os').name == 'nt' else '/dev/null', 'w'))
        r = post(self.client, '/api/auth/login/', {'username': '1', 'password': 'Legacy@1234'})
        self.assertEqual((r.status_code, r.json()['user']['role']), (200, 'admin'))
        call_command('bootstrap_admin', stdout=open('NUL' if __import__('os').name == 'nt' else '/dev/null', 'w'))   # آمن للتكرار
        self.assertEqual(UserProfile.objects.filter(user__username='1').count(), 1)
