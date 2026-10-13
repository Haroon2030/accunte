import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
import json
import os
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .models import Attachment, MatchRequest, User

PDF = b'%PDF-1.4\n%test\n'
XLSX = b'PK\x03\x04' + b'0' * 40


def make(username, role, **kw):
    u = User(username=username, role=role, name=kw.pop('name', username), **kw)
    u.set_password('Pass1234')
    u.save()
    return u


def login(user, portal='staff'):
    c = APIClient()
    r = c.post('/api/auth/login', {'username': user.username, 'password': 'Pass1234', 'portal': portal}, format='json')
    assert r.status_code == 200, r.content
    return c


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PortalTests(TestCase):
    def setUp(self):
        cache.clear()                                   # the login rate limit counts per minute across the whole run
        self.admin = make('1', 'admin', org='أسواق الرشيد')
        self.manager = make('2', 'manager')
        self.matcher = make('3', 'matcher')
        self.sup = make('4', 'supplier', org='شركة النخبة', code='S-1')
        self.sup2 = make('5', 'supplier', org='شركة أخرى', code='S-2')
        self.supervisor = make('7', 'supervisor')

    def new_request(self, c, name='kashf.pdf', body=PDF):
        return c.post('/api/requests/', {'dateFrom': '2026-01-01', 'dateTo': '2026-03-31', 'statement': SimpleUploadedFile(name, body)}, format='multipart')

    # ---- auth
    def test_one_login_for_every_role(self):
        for u in (self.sup, self.admin, self.manager, self.matcher):
            c = APIClient()
            r = c.post('/api/auth/login', {'username': u.username, 'password': 'Pass1234'}, format='json')
            self.assertEqual(r.status_code, 200, u.role)
            self.assertEqual(r.json()['user']['role'], u.role)

    def test_session_survives_a_reload(self):
        anon = APIClient().get('/api/auth/me')
        self.assertIsNone(anon.json()['user'])
        c = login(self.sup, 'supplier')
        me = c.get('/api/auth/me').json()['user']
        self.assertEqual((me['username'], me['role']), ('4', 'supplier'))      # /me recognises the signed-in user

    def test_wrong_password_and_suspended(self):
        c = APIClient()
        self.assertEqual(c.post('/api/auth/login', {'username': '1', 'password': 'nope'}, format='json').status_code, 400)
        self.matcher.is_active = False
        self.matcher.save()
        r = c.post('/api/auth/login', {'username': '3', 'password': 'Pass1234'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('موقوف', r.json()['detail'])

    def test_api_requires_login(self):
        self.assertIn(APIClient().get('/api/requests/').status_code, (401, 403))

    def test_change_password_rule(self):
        c = login(self.sup, 'supplier')
        self.assertEqual(c.post('/api/auth/change-password', {'password': '123'}, format='json').status_code, 400)
        self.assertEqual(c.post('/api/auth/change-password', {'password': 'NewPass99'}, format='json').status_code, 200)

    # ---- users
    def test_only_admin_manages_users(self):
        self.assertEqual(login(self.manager).get('/api/users/').status_code, 403)
        self.assertEqual(login(self.sup, 'supplier').get('/api/users/').status_code, 403)
        c = login(self.admin)
        self.assertEqual(len(c.get('/api/users/').json()), 6)

    def test_admin_creates_supplier_with_code_and_tax(self):
        c = login(self.admin)
        body = {'name': 'مورد جديد', 'username': '9', 'role': 'supplier', 'org': 'شركة الأمل', 'code': 'S-9', 'taxNo': '300999888700003', 'password': 'Temp1234'}
        r = c.post('/api/users/', body, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()['mustChange'])
        self.assertEqual(c.post('/api/users/', {**body, 'username': '10'}, format='json').status_code, 400)  # duplicate code
        self.assertEqual(c.post('/api/users/', {**body, 'username': '11', 'code': 'S-11', 'taxNo': '123'}, format='json').status_code, 400)

    def test_admin_sets_a_password_in_the_edit_form(self):
        c = login(self.admin)
        base = {'name': 'مطابق', 'username': '3', 'role': 'matcher', 'org': 'قسم'}
        r = c.patch(f'/api/users/{self.matcher.pk}/', {**base, 'password': '123'}, format='json')
        self.assertEqual(r.status_code, 400)                                           # too short
        r = c.patch(f'/api/users/{self.matcher.pk}/', {**base, 'password': '654321'}, format='json')
        self.assertEqual((r.status_code, r.json()['mustChange']), (200, False))
        self.assertTrue(login_ok('3', '654321'))
        r = c.patch(f'/api/users/{self.matcher.pk}/', {**base, 'password': '777777', 'mustChange': True}, format='json')
        self.assertTrue(r.json()['mustChange'])
        keep = {**base, 'password': ''}                                                # empty = unchanged
        c.patch(f'/api/users/{self.matcher.pk}/', keep, format='json')
        self.assertTrue(login_ok('3', '777777'))
        own = c.patch(f'/api/users/{self.admin.pk}/', {'name': 'مدير', 'username': '1', 'role': 'admin', 'password': '999999'}, format='json')
        self.assertEqual(own.status_code, 200)
        self.assertEqual(c.get('/api/users/').status_code, 200)                        # the admin is still signed in

    def test_admin_cannot_demote_or_stop_self_and_reset_returns_password(self):
        c = login(self.admin)
        r = c.patch(f'/api/users/{self.admin.pk}/', {'name': 'x', 'username': '1', 'role': 'manager'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(c.post(f'/api/users/{self.admin.pk}/toggle').status_code, 400)
        r = c.post(f'/api/users/{self.matcher.pk}/reset-password')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(login_ok(self.matcher.username, r.json()['password']))

    # ---- requests + files
    def test_supplier_uploads_pdf_and_isolation(self):
        c = login(self.sup, 'supplier')
        r = self.new_request(c)
        self.assertEqual(r.json()['period'], 'من 01/01/2026 إلى 31/03/2026')
        again = self.new_request(c)                                                       # a double click: same request answered, no copy
        self.assertEqual((again.status_code, again.json()['pk']), (200, r.json()['pk']))
        self.assertEqual(MatchRequest.objects.filter(supplier=self.sup).count(), 1)
        for bad in ({'dateFrom': '2026-05-01', 'dateTo': '2026-01-01'}, {'dateFrom': '2026-01-01'}, {'dateFrom': 'x', 'dateTo': 'y'}, {'dateFrom': '2026-01-01', 'dateTo': '2999-01-01'}, {}):
            self.assertEqual(c.post('/api/requests/', {**bad, 'statement': SimpleUploadedFile('k.pdf', PDF)}, format='multipart').status_code, 400)
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()
        self.assertTrue(data['id'].startswith('MT-'))
        self.assertEqual(data['statement']['name'], 'kashf.pdf')
        self.assertEqual(len(c.get('/api/requests/').json()), 1)
        other = login(self.sup2, 'supplier')
        self.assertEqual(other.get('/api/requests/').json(), [])
        self.assertEqual(other.get(f"/api/requests/{data['pk']}/").status_code, 404)
        self.assertEqual(other.get(data['statement']['url']).status_code, 404)
        self.assertEqual(c.get(data['statement']['url']).status_code, 200)
        self.assertEqual(login(self.matcher).get(data['statement']['url']).status_code, 200)

    def test_upload_validation(self):
        c = login(self.sup, 'supplier')
        self.assertEqual(self.new_request(c, 'a.xlsx', XLSX).status_code, 201)
        self.assertEqual(self.new_request(c, 'a.exe', b'MZ').status_code, 400)
        self.assertEqual(self.new_request(c, 'fake.pdf', b'not a pdf').status_code, 400)
        self.assertEqual(c.post('/api/requests/', {'period': 'x'}, format='multipart').status_code, 400)
        self.assertEqual(Attachment.objects.count(), 1)

    def test_request_workflow_and_chat(self):
        sup = login(self.sup, 'supplier')
        rid = self.new_request(sup).json()['pk']
        m = login(self.matcher)
        spv = login(self.supervisor)
        self.assertEqual(sup.post(f'/api/requests/{rid}/advance').status_code, 403)
        self.assertEqual(m.post(f'/api/requests/{rid}/advance', {'matcherId': self.matcher.pk}, format='json').status_code, 403)   # matchers cannot receive
        self.assertEqual(spv.post(f'/api/requests/{rid}/advance').status_code, 400)                                               # a matcher must be chosen
        self.assertEqual(spv.post(f'/api/requests/{rid}/advance', {'matcherId': self.manager.pk}, format='json').status_code, 400)  # only matchers can be chosen
        r = spv.post(f'/api/requests/{rid}/advance', {'matcherId': self.matcher.pk}, format='json').json()
        self.assertEqual((r['stage'], r['matcher']), (2, '3'))
        self.assertTrue(any('مشرف الدعم' in x['text'] for x in r['messages']))
        self.assertEqual(spv.post(f'/api/requests/{rid}/advance').status_code, 403)                                               # after receiving, the matcher works
        # the finance manager and the system admin may receive too
        for who in (self.manager, self.admin):
            rid2 = self.new_request(sup, f'k{who.pk}.pdf').json()['pk']
            r2 = login(who).post(f'/api/requests/{rid2}/advance', {'matcherId': self.matcher.pk}, format='json').json()
            self.assertEqual(r2['stage'], 2)
            self.assertTrue(any(dict(User.ROLES)[who.role] in x['text'] for x in r2['messages']))
        other = make('6', 'matcher')
        self.assertEqual(login(other).post(f'/api/requests/{rid}/advance').status_code, 403)
        self.assertEqual(m.post(f'/api/requests/{rid}/messages', {'text': 'مبكر'}, format='json').status_code, 403)
        self.assertEqual(m.post(f'/api/requests/{rid}/advance').json()['stage'], 3)
        r = m.post(f'/api/requests/{rid}/messages', {'text': 'أرسل الفاتورة', 'files': [SimpleUploadedFile('i.pdf', PDF)]}, format='multipart')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['from'], 'matcher')
        r = sup.post(f'/api/requests/{rid}/messages', {'text': 'تم'}, format='json')
        self.assertEqual(r.json()['from'], 'supplier')
        self.assertEqual(login(other).post(f'/api/requests/{rid}/messages', {'text': 'x'}, format='json').status_code, 403)
        self.assertEqual(m.post(f'/api/requests/{rid}/advance', {'fromStage': 2}, format='json').status_code, 409)   # a stale second click is refused
        done = m.post(f'/api/requests/{rid}/advance', {'fromStage': 3}, format='json').json()
        self.assertEqual(done['stage'], 4)
        # step 6: only the support staff send the reconciliation file, and the file is required
        spv = login(self.supervisor)
        self.assertEqual(m.post(f'/api/requests/{rid}/advance').status_code, 403)
        self.assertEqual(sup.post(f'/api/requests/{rid}/advance').status_code, 403)
        self.assertEqual(spv.post(f'/api/requests/{rid}/advance').status_code, 400)
        sent = spv.post(f'/api/requests/{rid}/advance', {'file': SimpleUploadedFile('match.pdf', PDF)}, format='multipart')
        self.assertEqual(sent.status_code, 200, sent.content)
        sent = sent.json()
        self.assertEqual(sent['stage'], 5)
        self.assertEqual(sent['result']['name'], 'match.pdf')
        self.assertEqual(sup.get(sent['result']['url']).status_code, 200)       # the supplier can download it
        self.assertEqual(login(self.sup2, 'supplier').get(sent['result']['url']).status_code, 404)
        self.assertEqual(spv.post(f'/api/requests/{rid}/advance').status_code, 400)
        kinds = [x['from'] for x in sent['messages']]
        self.assertEqual(kinds.count('system'), 4)

    # ---- complaints
    def test_complaint_flow(self):
        sup = login(self.sup, 'supplier')
        rid = self.new_request(sup).json()
        r = sup.post('/api/complaints/', {'category': 'تأخر في السداد', 'subject': 'تأخر', 'body': 'تفاصيل', 'related': rid['id'],
                                          'files': [SimpleUploadedFile('p.png', b'\x89PNG' + b'0' * 20)]}, format='multipart')
        self.assertEqual(r.status_code, 201, r.content)
        c = r.json()
        self.assertTrue(c['id'].startswith('SH-'))
        self.assertEqual(c['related'], rid['id'])
        self.assertEqual(len(c['messages'][0]['files']), 1)
        self.assertEqual(login(self.matcher).get('/api/complaints/').status_code, 403)
        self.assertEqual(login(self.sup2, 'supplier').get(f"/api/complaints/{c['pk']}/").status_code, 404)
        mgr = login(self.manager)
        self.assertEqual(len(mgr.get('/api/complaints/').json()), 1)
        self.assertEqual(sup.post(f"/api/complaints/{c['pk']}/advance").status_code, 403)
        self.assertEqual(mgr.post(f"/api/complaints/{c['pk']}/advance").json()['stage'], 2)
        self.assertEqual(mgr.post(f"/api/complaints/{c['pk']}/messages", {'text': 'نراجع'}, format='json').json()['from'], 'manager')
        self.assertEqual(mgr.post(f"/api/complaints/{c['pk']}/advance").json()['stage'], 3)
        self.assertEqual(sup.post(f"/api/complaints/{c['pk']}/messages", {'text': 'شكراً'}, format='json').status_code, 403)

    def test_complaint_related_must_be_own(self):
        other = login(self.sup2, 'supplier')
        rid = self.new_request(other).json()['id']
        r = login(self.sup, 'supplier').post('/api/complaints/', {'category': 'x', 'subject': 'y', 'body': 'z', 'related': rid}, format='json')
        self.assertEqual(r.status_code, 400)


def login_ok(username, pw):
    return APIClient().post('/api/auth/login', {'username': username, 'password': pw}, format='json').status_code == 200


class WipeLegacyTests(TransactionTestCase):
    """Runs on the throwaway test database only."""

    def test_wipes_only_the_old_app_and_only_once(self):
        with connection.cursor() as c:
            c.execute('DROP TABLE IF EXISTS portal_attachment')
        # a database that already belongs to this app is never touched
        call_command('wipe_legacy_database')
        self.assertIn('portal_user', connection.introspection.table_names())

    def test_refuses_unrelated_database_and_wipes_old_one(self):
        with connection.cursor() as c:
            for t in connection.introspection.table_names():
                c.execute('DROP TABLE ' + connection.ops.quote_name(t))
            c.execute('CREATE TABLE somebody_elses_data (id integer primary key)')
        with self.assertRaises(CommandError):
            call_command('wipe_legacy_database')
        self.assertIn('somebody_elses_data', connection.introspection.table_names())
        with connection.cursor() as c:
            c.execute('CREATE TABLE accounts_userprofile (id integer primary key)')
        call_command('wipe_legacy_database')
        self.assertEqual(connection.introspection.table_names(), [])
        call_command('migrate', verbosity=0)  # the new schema builds cleanly on the emptied database
        self.assertIn('portal_user', connection.introspection.table_names())


def login_status(username, pw):
    return APIClient().post('/api/auth/login', {'username': username, 'password': pw}, format='json').status_code


class BootstrapUsersTests(TestCase):
    ENTRIES = [
        {'username': '1', 'role': 'admin', 'name': 'مدير', 'password': 'Boot1234'},
        {'username': '4', 'role': 'supplier', 'name': 'مورد', 'org': 'شركة', 'code': 'S-1', 'taxNo': '300000000000003', 'password': 'Boot1234', 'forceChange': False},
    ]

    def run_cmd(self, entries):
        with mock.patch.dict(os.environ, {'BOOTSTRAP_USERS': json.dumps(entries)}):
            call_command('bootstrap_users')

    def test_creates_once_and_never_resets_existing(self):
        self.run_cmd(self.ENTRIES)
        admin, sup = User.objects.get(username='1'), User.objects.get(username='4')
        self.assertTrue(admin.check_password('Boot1234'))
        self.assertTrue(admin.must_change_password)       # default: choose own password at first login
        self.assertFalse(sup.must_change_password)
        self.assertEqual((sup.code, sup.tax_no, sup.org), ('S-1', '300000000000003', 'شركة'))
        admin.set_password('Changed99')
        admin.save()
        self.run_cmd(self.ENTRIES)                          # next deploy: nothing is overwritten
        self.assertTrue(User.objects.get(username='1').check_password('Changed99'))
        self.assertEqual(User.objects.count(), 2)

    def test_bad_config_fails_loudly(self):
        with self.assertRaises(CommandError):
            self.run_cmd([{'username': '9', 'role': 'wizard', 'password': 'x'}])
        with mock.patch.dict(os.environ, {'BOOTSTRAP_USERS': 'not json'}):
            with self.assertRaises(CommandError):
                call_command('bootstrap_users')

    def test_first_deploy_creates_only_the_admin_once(self):
        with mock.patch.dict(os.environ, {'BOOTSTRAP_USERS': ''}):
            call_command('bootstrap_users')
            admin = User.objects.get()
            self.assertEqual((admin.username, admin.role), ('1', 'admin'))
            self.assertTrue(admin.must_change_password)
            self.assertEqual(login_status('1', '526400'), 200)       # signs in, but the API stays locked until a new password
            self.assertEqual(APIClient().get('/api/users/').status_code, 403)
            admin.delete()
            User.objects.create(username='x', name='x')
            call_command('bootstrap_users')                            # later deploys never recreate it
            self.assertFalse(User.objects.filter(username='1').exists())


    def test_unused_first_admin_follows_the_default_but_a_used_one_does_not(self):
        with mock.patch.dict(os.environ, {'BOOTSTRAP_USERS': ''}):
            call_command('bootstrap_users')
            admin = User.objects.get(username='1')
            admin.set_password('Old12345')              # as if an earlier deploy used another default
            admin.save()
            call_command('bootstrap_users')
            self.assertTrue(User.objects.get(username='1').check_password('526400'))
            admin = User.objects.get(username='1')
            admin.set_password('Mine1234')
            admin.last_login = admin.created_at         # someone signed in
            admin.save()
            call_command('bootstrap_users')
            self.assertTrue(User.objects.get(username='1').check_password('Mine1234'))

    def test_admin_recovery_from_the_panel(self):
        User.objects.create(username='1', name='x', role='manager', is_active=False)
        env = {'BOOTSTRAP_USERS': '', 'ADMIN_FORCE_RESET': '1', 'ADMIN_PASSWORD': 'Recover77'}
        with mock.patch.dict(os.environ, env):
            call_command('bootstrap_users')
        u = User.objects.get(username='1')
        self.assertTrue(u.check_password('Recover77'))
        self.assertEqual((u.role, u.is_active, u.must_change_password), ('admin', True, True))
        with mock.patch.dict(os.environ, {'ADMIN_FORCE_RESET': '1', 'ADMIN_PASSWORD': ''}):
            with self.assertRaises(CommandError):
                call_command('bootstrap_users')


class SeedDemoTests(TestCase):
    def test_seed_is_marked_repeatable_and_removable(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from .models import Complaint, MatchRequest, Message
        with self.assertRaises(CommandError):
            call_command('seed_demo_data')                       # no supplier yet
        make('4', 'supplier', org='شركة', code='S-1')
        make('3', 'matcher')
        make('2', 'manager')
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp, STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
            real = MatchRequest.objects.create(supplier=User.objects.get(username='4'), period='حقيقي', notes='ملاحظة حقيقية', due_at='2030-01-01T00:00:00Z')
            call_command('seed_demo_data')
            self.assertEqual(sorted(MatchRequest.objects.exclude(pk=real.pk).values_list('stage', flat=True)), [1, 1, 2, 2, 3, 3, 4, 5])
            self.assertEqual(sorted(Complaint.objects.values_list('stage', flat=True)), [1, 1, 2, 2, 3, 3])
            self.assertTrue(Attachment.objects.count() >= 15)
            before = MatchRequest.objects.count()
            call_command('seed_demo_data')                       # second run adds nothing
            self.assertEqual(MatchRequest.objects.count(), before)
            call_command('seed_demo_data', '--clear')
            self.assertEqual(list(MatchRequest.objects.values_list('pk', flat=True)), [real.pk])   # real data untouched
            self.assertEqual((Complaint.objects.count(), Message.objects.count(), Attachment.objects.count()), (0, 0, 0))


class PagePermissionTests(TestCase):
    def setUp(self):
        cache.clear()                                   # the login rate limit counts per minute across the whole run
        self.admin = make('1', 'admin')
        self.matcher = make('3', 'matcher')
        self.sup = make('4', 'supplier', org='ش', code='S-1')

    def test_defaults_then_custom_pages_are_enforced(self):
        a = login(self.admin)
        m = login(self.matcher)
        self.assertEqual(m.get('/api/complaints/').status_code, 403)               # matcher: no manager page by default
        r = a.patch(f'/api/users/{self.matcher.pk}/', {'name': 'م', 'username': '3', 'role': 'matcher', 'pages': ['matcher', 'manager']}, format='json')
        self.assertEqual((r.status_code, r.json()['pages'], r.json()['customPages']), (200, ['matcher', 'manager'], True))
        self.assertEqual(login(self.matcher).get('/api/complaints/').status_code, 200)  # now allowed
        a.patch(f'/api/users/{self.matcher.pk}/', {'name': 'م', 'username': '3', 'role': 'matcher', 'pages': ['recon']}, format='json')
        m = login(self.matcher)
        self.assertEqual(m.get('/api/requests/').status_code, 403)                  # no matcher/manager page left
        self.assertEqual(m.get('/api/users/').status_code, 403)
        r = a.patch(f'/api/users/{self.matcher.pk}/', {'name': 'م', 'username': '3', 'role': 'matcher', 'pages': None}, format='json')
        self.assertEqual((r.json()['pages'], r.json()['customPages']), (['matcher', 'recon'], False))

    def test_page_rules(self):
        a = login(self.admin)
        base = {'name': 'x', 'role': 'matcher'}
        self.assertEqual(a.patch(f'/api/users/{self.matcher.pk}/', {**base, 'username': '3', 'pages': []}, format='json').status_code, 400)
        self.assertEqual(a.patch(f'/api/users/{self.matcher.pk}/', {**base, 'username': '3', 'pages': ['supplier']}, format='json').status_code, 400)
        self.assertEqual(a.patch(f'/api/users/{self.sup.pk}/', {'name': 'x', 'username': '4', 'role': 'supplier', 'org': 'ش', 'code': 'S-1', 'pages': ['users']}, format='json').status_code, 400)
        own = a.patch(f'/api/users/{self.admin.pk}/', {'name': 'x', 'username': '1', 'role': 'admin', 'pages': ['matcher']}, format='json')
        self.assertEqual(own.status_code, 400)                                        # cannot lock yourself out of the users page
        created = a.post('/api/users/', {'name': 'جديد', 'username': '8', 'role': 'matcher', 'password': '1234', 'pages': ['manager', 'users']}, format='json')
        self.assertEqual((created.status_code, created.json()['pages']), (201, ['manager', 'users']))
        role_change = a.patch(f'/api/users/{self.matcher.pk}/', {'name': 'x', 'username': '3', 'role': 'manager'}, format='json')
        self.assertEqual(role_change.json()['pages'], ['matcher', 'manager', 'recon'])   # new role, its own defaults
