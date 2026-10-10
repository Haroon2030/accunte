import io
import json
import urllib.error
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.models import Role, UserProfile

from . import client
from .client import WhatsAppError

User = get_user_model()
SECRET = 'sk-test-SECRET-KEY-123'
CFG = dict(WHATSAPP_ENABLED=True, EVOLUTION_API_URL='http://evo.test:8081', EVOLUTION_API_KEY=SECRET,
           EVOLUTION_INSTANCE='hr', EVOLUTION_API_TIMEOUT=5, WHATSAPP_DEFAULT_COUNTRY='966')
PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=='


def make_user(username, role_type):
    role, _ = Role.objects.get_or_create(role_type=role_type, defaults={'name': f'r-{role_type}', 'is_system_role': True})
    u = User.objects.create_user(username, password='x-Pass-12345')
    UserProfile.objects.create(user=u, role=role)
    return u


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(routes):
    """routes: {(METHOD, path-prefix): dict | HTTPError-code int}. يسجّل الطلبات في fake.calls."""
    calls = []

    def _open(req, timeout=None):
        path = req.full_url.split('evo.test:8081', 1)[1]
        calls.append((req.get_method(), path, dict(req.header_items()), req.data))
        for (method, prefix), result in routes.items():
            if method == req.get_method() and path.startswith(prefix):
                if isinstance(result, int):
                    raise urllib.error.HTTPError(req.full_url, result, 'err', {}, io.BytesIO(b'{}'))
                if isinstance(result, Exception):
                    raise result
                return FakeResp(json.dumps(result).encode())
        raise AssertionError(f'unexpected call {req.get_method()} {path}')

    _open.calls = calls
    return _open


@override_settings(**CFG)
class ClientTests(TestCase):
    def test_connection_state_mapping(self):
        for payload, expected in (({'instance': {'state': 'open'}}, 'open'), ({'instance': {'state': 'connecting'}}, 'connecting'),
                                  ({'instance': {'state': 'weird'}}, 'close')):
            with mock.patch('urllib.request.urlopen', fake_urlopen({('GET', '/instance/connectionState/hr'): payload})):
                self.assertEqual(client.connection_state(), expected)

    def test_missing_instance_is_not_found(self):
        with mock.patch('urllib.request.urlopen', fake_urlopen({('GET', '/instance/connectionState/hr'): 404})):
            self.assertEqual(client.connection_state(), 'not_found')

    def test_api_key_sent_as_header_only(self):
        f = fake_urlopen({('GET', '/instance/connectionState/hr'): {'instance': {'state': 'open'}}})
        with mock.patch('urllib.request.urlopen', f):
            client.connection_state()
        method, path, headers, _ = f.calls[0]
        self.assertEqual(headers['Apikey'], SECRET)
        self.assertNotIn(SECRET, path)

    def test_qr_creates_missing_instance_then_connects(self):
        routes = {('GET', '/instance/connectionState/hr'): 404, ('POST', '/instance/create'): {},
                  ('GET', '/instance/connect/hr'): {'base64': PNG, 'pairingCode': 'ABCD-1234'}}
        f = fake_urlopen(routes)
        with mock.patch('urllib.request.urlopen', f):
            out = client.request_qr()
        self.assertEqual(out, {'qr': PNG, 'pairing_code': 'ABCD-1234'})
        body = json.loads([c for c in f.calls if c[0] == 'POST'][0][3])
        self.assertEqual(body['instanceName'], 'hr')
        self.assertEqual(body['integration'], 'WHATSAPP-BAILEYS')

    def test_qr_rejects_non_png_data(self):
        for bad in ('javascript:alert(1)', 'data:text/html;base64,PHNjcmlwdD4=', PNG + '"onerror="x', 'https://evil/x.png'):
            routes = {('GET', '/instance/connectionState/hr'): {'instance': {'state': 'close'}},
                      ('GET', '/instance/connect/hr'): {'base64': bad}}
            with mock.patch('urllib.request.urlopen', fake_urlopen(routes)):
                self.assertEqual(client.request_qr()['qr'], '', bad)

    def test_errors_are_arabic_and_never_leak_key(self):
        for code in (401, 500):
            with mock.patch('urllib.request.urlopen', fake_urlopen({('GET', '/instance/connectionState/hr'): code})):
                with self.assertRaises(WhatsAppError) as cm:
                    client.connection_state()
                self.assertNotIn(SECRET, str(cm.exception))
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('refused')):
            with self.assertRaises(WhatsAppError) as cm:
                client.connection_state()
            self.assertIn('تعذر الاتصال', str(cm.exception))

    def test_instance_info(self):
        payload = [{'ownerJid': '966501234567@s.whatsapp.net', 'profileName': 'الشركة'}]
        with mock.patch('urllib.request.urlopen', fake_urlopen({('GET', '/instance/fetchInstances'): payload})):
            self.assertEqual(client.instance_info(), {'number': '966501234567', 'name': 'الشركة'})

    def test_number_normalisation(self):
        for raw in ('0501234567', '501234567', '+966501234567', '00966501234567', '966 50 123 4567'):
            self.assertEqual(client.normalize_number(raw), '966501234567', raw)
        self.assertEqual(client.normalize_number('+20 100 123 4567'), '201001234567')
        for bad in ('', 'abc', '123'):
            self.assertIsNone(client.normalize_number(bad))

    def test_send_text_payload_and_validation(self):
        f = fake_urlopen({('POST', '/message/sendText/hr'): {'key': {}}})
        with mock.patch('urllib.request.urlopen', f):
            client.send_text('0501234567', ' مرحبا ')
        self.assertEqual(json.loads(f.calls[0][3]), {'number': '966501234567', 'text': 'مرحبا'})
        for number, text in (('abc', 'x'), ('0501234567', '  '), ('0501234567', 'x' * 4001)):
            with self.assertRaises(WhatsAppError):
                client.send_text(number, text)

    def test_disabled_and_unconfigured(self):
        with override_settings(WHATSAPP_ENABLED=False):
            with self.assertRaises(WhatsAppError):
                client.connection_state()
        with override_settings(EVOLUTION_API_KEY=''):
            self.assertFalse(client.is_configured())
            with self.assertRaises(WhatsAppError):
                client.connection_state()
        with override_settings(EVOLUTION_INSTANCE='bad name/../x'):
            self.assertFalse(client.is_configured())


@override_settings(**CFG)
class ViewTests(TestCase):
    def setUp(self):
        self.cfo = make_user('cfo', Role.RoleType.CFO)
        self.acc = make_user('acc', Role.RoleType.ACCOUNTANT)

    def test_page_access_by_role(self):
        url = reverse('whatsapp:connect')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.acc)
        self.assertEqual(self.client.get(url).status_code, 302)
        for name in ('cfo',):
            self.client.force_login(User.objects.get(username=name))
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_api_endpoints_return_json_errors_not_redirects(self):
        for name, method in (('status', 'get'), ('qr', 'post'), ('disconnect', 'post'), ('test', 'post')):
            r = getattr(self.client, method)(reverse(f'whatsapp:{name}'))
            self.assertEqual(r.status_code, 401, name)
        self.client.force_login(self.acc)
        for name, method in (('status', 'get'), ('qr', 'post'), ('disconnect', 'post'), ('test', 'post')):
            r = getattr(self.client, method)(reverse(f'whatsapp:{name}'))
            self.assertEqual(r.status_code, 403, name)

    def test_state_changing_endpoints_reject_get(self):
        self.client.force_login(self.cfo)
        for name in ('qr', 'disconnect', 'test'):
            self.assertEqual(self.client.get(reverse(f'whatsapp:{name}')).status_code, 405, name)

    def test_status_connected_includes_account(self):
        routes = {('GET', '/instance/connectionState/hr'): {'instance': {'state': 'open'}},
                  ('GET', '/instance/fetchInstances'): [{'ownerJid': '966501234567@s.whatsapp.net', 'profileName': 'X'}]}
        self.client.force_login(self.cfo)
        with mock.patch('urllib.request.urlopen', fake_urlopen(routes)):
            data = self.client.get(reverse('whatsapp:status')).json()
        self.assertEqual((data['state'], data['account']['number']), ('open', '966501234567'))

    def test_qr_flow_and_no_secret_in_any_response(self):
        routes = {('GET', '/instance/connectionState/hr'): {'instance': {'state': 'close'}},
                  ('GET', '/instance/connect/hr'): {'base64': PNG}}
        self.client.force_login(self.cfo)
        with mock.patch('urllib.request.urlopen', fake_urlopen(routes)):
            r = self.client.post(reverse('whatsapp:qr'))
            page = self.client.get(reverse('whatsapp:connect'))
        self.assertEqual(r.json()['qr'], PNG)
        self.assertNotIn(SECRET, r.content.decode())
        self.assertNotIn(SECRET, page.content.decode())

    def test_qr_when_already_connected_returns_open(self):
        routes = {('GET', '/instance/connectionState/hr'): {'instance': {'state': 'open'}}}
        self.client.force_login(self.cfo)
        with mock.patch('urllib.request.urlopen', fake_urlopen(routes)):
            data = self.client.post(reverse('whatsapp:qr')).json()
        self.assertEqual((data['ok'], data['state'], data['qr']), (True, 'open', ''))

    def test_upstream_failure_gives_502_with_arabic_message(self):
        self.client.force_login(self.cfo)
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('down')):
            r = self.client.get(reverse('whatsapp:status'))
        self.assertEqual(r.status_code, 502)
        self.assertIn('تعذر الاتصال', r.json()['error'])
        self.assertNotIn(SECRET, r.content.decode())

    def test_disconnect_and_test_send_are_audited_without_content_leak(self):
        routes = {('DELETE', '/instance/logout/hr'): {}, ('POST', '/message/sendText/hr'): {}}
        self.client.force_login(self.cfo)
        with mock.patch('urllib.request.urlopen', fake_urlopen(routes)):
            self.assertTrue(self.client.post(reverse('whatsapp:disconnect')).json()['ok'])
            self.assertTrue(self.client.post(reverse('whatsapp:test'), {'number': '0501234567', 'text': 'سر'}).json()['ok'])
        logs = AuditLog.objects.filter(entity_type='whatsapp.Instance').order_by('id')
        self.assertEqual(logs.count(), 2)
        sent = logs[1]
        self.assertEqual(sent.new_state['to'], '96650123****')
        self.assertNotIn('سر', json.dumps(sent.new_state, ensure_ascii=False))
        self.assertEqual(sent.actor, self.cfo)

    def test_invalid_test_number_rejected(self):
        self.client.force_login(self.cfo)
        r = self.client.post(reverse('whatsapp:test'), {'number': 'abc'})
        self.assertEqual(r.status_code, 502)

    @override_settings(WHATSAPP_ENABLED=False)
    def test_disabled_page_shows_notice(self):
        self.client.force_login(self.cfo)
        html = self.client.get(reverse('whatsapp:connect')).content.decode()
        self.assertIn('معطّل', html)
        self.assertNotIn('x-data="waLink()"', html)
