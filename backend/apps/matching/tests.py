import json
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from apps.accounts.models import UserProfile
from apps.accounts.tests import make_user

from .models import Attachment, Complaint, MatchRequest, Message

Role = UserProfile.Role
TMP = tempfile.mkdtemp()


def pdf(name='statement.pdf', size=100):
    return SimpleUploadedFile(name, b'%PDF-' + b'0' * size, content_type='application/pdf')


def j(resp):
    return resp.json()


@override_settings(PRIVATE_MEDIA_ROOT=TMP)
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.sup = make_user('nokhba', Role.SUPPLIER, org='شركة النخبة')
        self.other_sup = make_user('fajr', Role.SUPPLIER, org='مصنع الفجر')
        self.m1 = make_user('khaled', Role.MATCHER)
        self.m2 = make_user('mona', Role.MATCHER)
        self.mgr = make_user('salman', Role.MANAGER)
        self.admin = make_user('boss', Role.ADMIN)
        # ملفات التخزين الخاص في مجلد مؤقت
        from .models import Attachment as A
        from django.core.files.storage import FileSystemStorage
        A._meta.get_field('file').storage = FileSystemStorage(location=TMP)

    def as_user(self, user):
        c = Client()
        c.force_login(user)
        return c

    def new_request(self, user=None, period='سبتمبر 2026'):
        c = self.as_user(user or self.sup)
        r = c.post('/api/requests/', {'period': period, 'notes': 'ملاحظة', 'file': pdf()})
        self.assertEqual(r.status_code, 201, r.content)
        return j(r)['request']


class RequestFlowTests(Base):
    def test_supplier_creates_request_with_statement(self):
        req = self.new_request()
        self.assertTrue(req['id'].startswith('MT-'))
        self.assertEqual((req['stage'], req['supplier'], req['matcher']), (1, 'شركة النخبة', None))
        self.assertEqual(req['statement']['name'], 'statement.pdf')
        self.assertEqual(len(req['reached']), 5)
        self.assertIsNotNone(req['reached'][1])
        self.assertEqual(MatchRequest.objects.count(), 1)

    def test_creation_validation(self):
        c = self.as_user(self.sup)
        self.assertEqual(c.post('/api/requests/', {'period': 'x'}).status_code, 400)                         # بلا كشف
        bad = SimpleUploadedFile('virus.exe', b'MZ')
        self.assertEqual(c.post('/api/requests/', {'period': 'x', 'file': bad}).status_code, 400)
        self.assertEqual(self.as_user(self.m1).post('/api/requests/', {'period': 'x', 'file': pdf()}).status_code, 403)

    @override_settings(MAX_UPLOAD_BYTES=50)
    def test_file_size_limit(self):
        r = self.as_user(self.sup).post('/api/requests/', {'period': 'x', 'file': pdf(size=500)})
        self.assertEqual(r.status_code, 400)

    def test_visibility_by_role(self):
        mine = self.new_request(self.sup)
        theirs = self.new_request(self.other_sup)
        for user, expected in ((self.sup, {mine['id']}), (self.other_sup, {theirs['id']}),
                               (self.mgr, {mine['id'], theirs['id']}), (self.admin, {mine['id'], theirs['id']}),
                               (self.m1, {mine['id'], theirs['id']})):                               # غير مسندة: يراها كل مطابق
            ids = {r['id'] for r in j(self.as_user(user).get('/api/bootstrap/'))['requests']}
            self.assertEqual(ids, expected, user.username)

    def test_full_stage_flow_and_matcher_assignment(self):
        req = self.new_request()
        code = req['id']
        m1 = self.as_user(self.m1)
        r = j(m1.post(f'/api/requests/{code}/advance/'))['request']
        self.assertEqual((r['stage'], r['matcher']), (2, 'khaled'))
        self.assertIsNotNone(r['reached'][2])
        self.assertEqual(r['messages'][-1]['from'], 'system')
        # مطابق آخر لا يرى الطلب بعد إسناده ولا يحرّكه
        self.assertEqual(self.as_user(self.m2).post(f'/api/requests/{code}/advance/').status_code, 404)
        self.assertEqual(j(m1.post(f'/api/requests/{code}/advance/'))['request']['stage'], 3)
        self.assertEqual(j(m1.post(f'/api/requests/{code}/advance/'))['request']['stage'], 4)
        self.assertEqual(m1.post(f'/api/requests/{code}/advance/').status_code, 400)
        # المورد لا يحرّك الطلب
        self.assertEqual(self.as_user(self.sup).post(f'/api/requests/{code}/advance/').status_code, 403)

    def test_messaging_rules(self):
        code = self.new_request()['id']
        sup, m1 = self.as_user(self.sup), self.as_user(self.m1)
        self.assertEqual(sup.post(f'/api/requests/{code}/messages/', {'text': 'مرحباً'}).status_code, 400)   # قبل مرحلة الاستيضاح
        m1.post(f'/api/requests/{code}/advance/')
        m1.post(f'/api/requests/{code}/advance/')                                                             # → 3
        r = m1.post(f'/api/requests/{code}/messages/', {'text': 'ظهر فرق 4,320 ر.س', 'files': [pdf('notice.pdf')]})
        self.assertEqual(r.status_code, 201)
        msgs = j(r)['request']['messages']
        self.assertEqual(msgs[-1]['from'], 'matcher')
        self.assertEqual(msgs[-1]['files'][0]['name'], 'notice.pdf')
        reply = sup.post(f'/api/requests/{code}/messages/', {'text': 'أرفقت الإشعار'})
        self.assertEqual(j(reply)['request']['messages'][-1]['from'], 'supplier')
        self.assertEqual(sup.post(f'/api/requests/{code}/messages/', {'text': '  '}).status_code, 400)       # فارغة
        # المدير يكتب بصفة مراقب
        obs = self.as_user(self.mgr).post(f'/api/requests/{code}/messages/', {'text': 'ملاحظة', 'from': 'manager'})
        self.assertEqual(j(obs)['request']['messages'][-1]['from'], 'manager')
        # المورد لا ينتحل صفة المطابق
        fake = sup.post(f'/api/requests/{code}/messages/', {'text': 'x', 'from': 'matcher'})
        self.assertEqual(j(fake)['request']['messages'][-1]['from'], 'supplier')
        # مورد آخر لا يصل إليها
        self.assertEqual(self.as_user(self.other_sup).post(f'/api/requests/{code}/messages/', {'text': 'x'}).status_code, 404)


class ComplaintTests(Base):
    def make_complaint(self, **extra):
        data = {'category': 'تأخر في السداد', 'subject': 'دفعة متأخرة', 'body': 'لم تصلنا الدفعة'}
        data.update(extra)
        r = self.as_user(self.sup).post('/api/complaints/', data)
        self.assertEqual(r.status_code, 201, r.content)
        return j(r)['complaint']

    def test_create_and_visibility(self):
        c = self.make_complaint()
        self.assertTrue(c['id'].startswith('SH-'))
        self.assertEqual((c['stage'], c['messages'][0]['from'], c['messages'][0]['text']), (1, 'supplier', 'لم تصلنا الدفعة'))
        ids = lambda user: {x['id'] for x in j(self.as_user(user).get('/api/bootstrap/'))['complaints']}
        self.assertEqual(ids(self.sup), {c['id']})
        self.assertEqual(ids(self.mgr), {c['id']})
        self.assertEqual(ids(self.other_sup), set())
        self.assertEqual(ids(self.m1), set())                       # المطابقون لا يطّلعون على الشكاوى

    def test_related_request_must_belong_to_supplier(self):
        mine = self.new_request(self.sup)['id']
        theirs = self.new_request(self.other_sup)['id']
        self.assertEqual(self.make_complaint(related=mine)['related'], mine)
        r = self.as_user(self.sup).post('/api/complaints/', {'category': 'أخرى', 'subject': 's', 'body': 'b', 'related': theirs})
        self.assertEqual(r.status_code, 400)

    def test_manager_flow_and_messages(self):
        code = self.make_complaint()['id']
        mgr, sup = self.as_user(self.mgr), self.as_user(self.sup)
        self.assertEqual(j(mgr.post(f'/api/complaints/{code}/advance/'))['complaint']['stage'], 2)
        self.assertEqual(sup.post(f'/api/complaints/{code}/advance/').status_code, 403)
        self.assertEqual(self.as_user(self.m1).post(f'/api/complaints/{code}/advance/').status_code, 403)
        r = mgr.post(f'/api/complaints/{code}/messages/', {'text': 'نراجع الشكوى'})
        self.assertEqual(j(r)['complaint']['messages'][-1]['from'], 'manager')
        self.assertEqual(j(mgr.post(f'/api/complaints/{code}/advance/'))['complaint']['stage'], 3)
        self.assertEqual(mgr.post(f'/api/complaints/{code}/advance/').status_code, 400)
        self.assertEqual(sup.post(f'/api/complaints/{code}/messages/', {'text': 'شكراً'}).status_code, 400)  # أُغلقت

    def test_validation(self):
        c = self.as_user(self.sup)
        self.assertEqual(c.post('/api/complaints/', {'category': 'نوع غير معروف', 'subject': 's', 'body': 'b'}).status_code, 400)
        self.assertEqual(c.post('/api/complaints/', {'category': 'أخرى', 'subject': '', 'body': 'b'}).status_code, 400)


class AttachmentAccessTests(Base):
    def test_download_is_permission_checked(self):
        req = self.new_request()
        att = Attachment.objects.get(statement_of__code=req['id'])
        url = f'/api/attachments/{att.pk}/'
        self.assertEqual(self.as_user(self.sup).get(url).status_code, 200)
        self.assertEqual(self.as_user(self.mgr).get(url).status_code, 200)
        self.assertEqual(self.as_user(self.other_sup).get(url).status_code, 404)
        self.assertEqual(Client().get(url).status_code, 401)

    def test_complaint_attachments_hidden_from_matchers(self):
        r = self.as_user(self.sup).post('/api/complaints/', {'category': 'أخرى', 'subject': 's', 'body': 'b', 'files': [pdf('proof.pdf')]})
        att = Attachment.objects.get(name='proof.pdf')
        self.assertEqual(self.as_user(self.mgr).get(f'/api/attachments/{att.pk}/').status_code, 200)
        self.assertEqual(self.as_user(self.m1).get(f'/api/attachments/{att.pk}/').status_code, 404)


class SeenAndBootstrapTests(Base):
    def test_seen_roundtrip_and_validation(self):
        code = self.new_request()['id']
        c = self.as_user(self.sup)
        self.assertEqual(j(c.get('/api/bootstrap/'))['seen'], {})
        r = c.post('/api/seen/', json.dumps({'key': f'{code}:supplier'}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertIn(f'{code}:supplier', j(c.get('/api/bootstrap/'))['seen'])
        bad = c.post('/api/seen/', json.dumps({'key': 'drop table'}), content_type='application/json')
        self.assertEqual(bad.status_code, 400)

    def test_users_only_in_bootstrap_for_admin(self):
        self.assertNotIn('users', j(self.as_user(self.mgr).get('/api/bootstrap/')))
        self.assertIn('users', j(self.as_user(self.admin).get('/api/bootstrap/')))
