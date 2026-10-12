import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .models import Attachment, User

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
        self.admin = make('1', 'admin', org='أسواق الراشد')
        self.manager = make('2', 'manager')
        self.matcher = make('3', 'matcher')
        self.sup = make('4', 'supplier', org='شركة النخبة', code='S-1')
        self.sup2 = make('5', 'supplier', org='شركة أخرى', code='S-2')

    def new_request(self, c, name='kashf.pdf', body=PDF):
        return c.post('/api/requests/', {'period': 'سبتمبر 2026', 'statement': SimpleUploadedFile(name, body)}, format='multipart')

    # ---- auth
    def test_portals_are_separate(self):
        c = APIClient()
        r = c.post('/api/auth/login', {'username': '4', 'password': 'Pass1234', 'portal': 'staff'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = c.post('/api/auth/login', {'username': '1', 'password': 'Pass1234', 'portal': 'supplier'}, format='json')
        self.assertEqual(r.status_code, 400)
        login(self.sup, 'supplier')
        login(self.admin, 'staff')

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
        self.assertEqual(c.post('/api/auth/change-password', {'password': '123456'}, format='json').status_code, 400)
        self.assertEqual(c.post('/api/auth/change-password', {'password': 'NewPass99'}, format='json').status_code, 200)

    # ---- users
    def test_only_admin_manages_users(self):
        self.assertEqual(login(self.manager).get('/api/users/').status_code, 403)
        self.assertEqual(login(self.sup, 'supplier').get('/api/users/').status_code, 403)
        c = login(self.admin)
        self.assertEqual(len(c.get('/api/users/').json()), 5)

    def test_admin_creates_supplier_with_code_and_tax(self):
        c = login(self.admin)
        body = {'name': 'مورد جديد', 'username': '9', 'role': 'supplier', 'org': 'شركة الأمل', 'code': 'S-9', 'taxNo': '300999888700003', 'password': 'Temp1234'}
        r = c.post('/api/users/', body, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()['mustChange'])
        self.assertEqual(c.post('/api/users/', {**body, 'username': '10'}, format='json').status_code, 400)  # duplicate code
        self.assertEqual(c.post('/api/users/', {**body, 'username': '11', 'code': 'S-11', 'taxNo': '123'}, format='json').status_code, 400)

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
        self.assertEqual(sup.post(f'/api/requests/{rid}/advance').status_code, 403)
        r = m.post(f'/api/requests/{rid}/advance').json()
        self.assertEqual((r['stage'], r['matcher']), (2, '3'))
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
        done = m.post(f'/api/requests/{rid}/advance').json()
        self.assertEqual(done['stage'], 4)
        self.assertEqual(m.post(f'/api/requests/{rid}/advance').status_code, 400)
        kinds = [x['from'] for x in done['messages']]
        self.assertEqual(kinds.count('system'), 3)

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
