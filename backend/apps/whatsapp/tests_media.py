import base64
import json
import shutil
import tempfile
from unittest import mock

from django.core.files.storage import FileSystemStorage
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.models import Role

from . import client, services
from .client import WhatsAppError
from .models import ConversationMessage, SupplierConversation
from .tests_inbox import CFG, NUMBER, make_user, upsert

M = ConversationMessage
PDF = b'%PDF-1.4 fake pdf bytes'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==')


def b64(blob):
    return base64.b64encode(blob).decode()


def doc_event(msg_id='DOC1', name='InvoiceView.pdf'):
    return upsert(msg_id, message={'documentMessage': {'fileName': name, 'mimetype': 'application/pdf'}})


class MediaBase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp()
        M._meta.get_field('media_file').storage = FileSystemStorage(location=cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()


@override_settings(**CFG)
class ClientFetchTests(TestCase):
    def call(self, response):
        with mock.patch('apps.whatsapp.client._request', return_value=response) as req:
            try:
                return client.fetch_media('WA-1'), req
            except WhatsAppError as exc:
                return exc, req

    def test_parses_base64_mimetype_and_name(self):
        (blob, mime, name), req = self.call({'base64': b64(PDF), 'mimetype': 'Application/PDF; charset=x', 'fileName': 'a.pdf'})
        self.assertEqual((blob, mime, name), (PDF, 'application/pdf', 'a.pdf'))
        method, path, body = req.call_args[0]
        self.assertEqual((method, path), ('POST', '/chat/getBase64FromMediaMessage/hr'))
        self.assertEqual(body['message']['key']['id'], 'WA-1')

    def test_accepts_data_uri_prefix(self):
        (blob, mime, _), _ = self.call({'base64': 'data:application/pdf;base64,' + b64(PDF), 'mimetype': 'application/pdf'})
        self.assertEqual(blob, PDF)

    def test_rejects_bad_responses(self):
        for resp in ({}, {'base64': ''}, {'base64': '!!!not base64!!!'}, {'base64': b64(b'')}, None, []):
            result, _ = self.call(resp)
            self.assertIsInstance(result, WhatsAppError, resp)

    def test_size_limit_before_and_after_decoding(self):
        with mock.patch.object(client, 'MAX_MEDIA_BYTES', 10):
            result, _ = self.call({'base64': b64(b'x' * 100)})
            self.assertIn('حجم الملف', str(result))
            result, _ = self.call({'base64': b64(b'x' * 8), 'mimetype': 'text/plain'})
            self.assertEqual(result[0], b'x' * 8)

    def test_requires_message_id(self):
        with self.assertRaises(WhatsAppError):
            client.fetch_media('')


@override_settings(**CFG)
class StoreMediaTests(MediaBase):
    def msg(self, **kw):
        conv, _ = SupplierConversation.objects.get_or_create(contact_number=NUMBER)
        defaults = dict(conversation=conv, direction='in', wa_message_id='W1', kind='document', media_name='InvoiceView.pdf')
        defaults.update(kw)
        return M.objects.create(**defaults)

    def test_stores_file_with_metadata_and_is_idempotent(self):
        m = self.msg()
        with mock.patch('apps.whatsapp.client.fetch_media', return_value=(PDF, 'application/pdf', 'InvoiceView.pdf')) as f:
            services.fetch_and_store_media(m.pk)
            services.fetch_and_store_media(m.pk)         # لا جلب ثانٍ
        self.assertEqual(f.call_count, 1)
        m.refresh_from_db()
        self.assertEqual((m.media_mimetype, m.media_size, m.media_error), ('application/pdf', len(PDF), ''))
        self.assertEqual(m.media_file.read(), PDF)
        self.assertTrue(m.media_file.name.endswith('.pdf'))

    def test_hostile_file_names_are_neutralised(self):
        for i, name in enumerate(('../../etc/passwd', 'a/b\\c.pdf', 'x.PHP', '..', 'ملف عربي.pdf', 'a' * 300 + '.pdf', '')):
            m = self.msg(wa_message_id=f'H{i}', media_name=name)
            with mock.patch('apps.whatsapp.client.fetch_media', return_value=(PDF, 'application/pdf', '')):
                services.fetch_and_store_media(m.pk)
            m.refresh_from_db()
            stored = m.media_file.name
            self.assertNotIn('..', stored, name)
            self.assertNotIn('\\', stored, name)
            self.assertTrue(stored.startswith('reconciliation/'), stored)     # ضمن مجلد التخزين لا خارجه
            self.assertLessEqual(len(stored.rsplit('/', 1)[-1]), 80, name)

    def test_missing_extension_taken_from_mimetype(self):
        m = self.msg(media_name='', kind='image')
        with mock.patch('apps.whatsapp.client.fetch_media', return_value=(PNG, 'image/png', '')):
            services.fetch_and_store_media(m.pk)
        m.refresh_from_db()
        self.assertTrue(m.media_file.name.endswith('.png'))

    def test_failure_records_error_and_raises(self):
        m = self.msg()
        with mock.patch('apps.whatsapp.client.fetch_media', side_effect=WhatsAppError('غير موجود')):
            with self.assertRaises(WhatsAppError):
                services.fetch_and_store_media(m.pk)
        m.refresh_from_db()
        self.assertEqual((bool(m.media_file), m.media_error), (False, 'غير موجود'))

    def test_text_and_idless_messages_rejected(self):
        for kw in ({'kind': 'text'}, {'wa_message_id': None}):
            m = self.msg(**kw) if 'wa_message_id' not in kw else self.msg(wa_message_id=None)
            with self.assertRaises(WhatsAppError):
                services.fetch_and_store_media(m.pk)


@override_settings(**CFG)
class IngestFetchTests(MediaBase):
    def post(self, payload):
        return self.client.post(reverse('whatsapp:webhook', args=['whsec-test-123']), json.dumps(payload),
                                content_type='application/json')

    def test_document_event_stores_message_then_fetches_file(self):
        with mock.patch('apps.whatsapp.client.fetch_media', return_value=(PDF, 'application/pdf', 'InvoiceView.pdf')) as f:
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.post(doc_event())
        self.assertEqual(resp.status_code, 200)
        m = M.objects.get(wa_message_id='DOC1')
        self.assertEqual((m.kind, m.media_name, bool(m.media_file), m.media_size), ('document', 'InvoiceView.pdf', True, len(PDF)))
        f.assert_called_once_with('DOC1')

    def test_fetch_failure_does_not_break_webhook_and_keeps_message(self):
        with mock.patch('apps.whatsapp.client.fetch_media', side_effect=WhatsAppError('لا يحتفظ بالرسالة')):
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.post(doc_event())
        self.assertEqual(resp.status_code, 200)
        m = M.objects.get(wa_message_id='DOC1')
        self.assertEqual((bool(m.media_file), m.media_error), (False, 'لا يحتفظ بالرسالة'))

    def test_duplicate_event_does_not_refetch(self):
        with mock.patch('apps.whatsapp.client.fetch_media', return_value=(PDF, 'application/pdf', '')) as f:
            with self.captureOnCommitCallbacks(execute=True):
                self.post(doc_event())
                self.post(doc_event())
        self.assertEqual(f.call_count, 1)
        self.assertEqual(M.objects.count(), 1)

    def test_text_message_never_fetches(self):
        with mock.patch('apps.whatsapp.client.fetch_media') as f:
            with self.captureOnCommitCallbacks(execute=True):
                self.post(upsert('T1', text='مرحبا'))
        f.assert_not_called()

    @override_settings(WHATSAPP_ASYNC_DISPATCH=True)
    def test_async_mode_uses_background_thread(self):
        with mock.patch('apps.whatsapp.services.threading.Thread') as thread:
            with self.captureOnCommitCallbacks(execute=True):
                self.post(doc_event())
        self.assertTrue(thread.called)
        self.assertTrue(thread.return_value.start.called)



