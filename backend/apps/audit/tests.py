from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import AuditLog, ImmutableError
from .services import log_action, sanitize

User = get_user_model()


class ImmutabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u1', password='x-Pass-12345')
        self.log = log_action(AuditLog.Action.CREATE, entity_type='t.T', entity_id=1, actor=self.user)

    def test_cannot_modify(self):
        self.log.reason = 'تعديل'
        with self.assertRaises(ImmutableError):
            self.log.save()

    def test_cannot_delete(self):
        with self.assertRaises(ImmutableError):
            self.log.delete()
        with self.assertRaises(ImmutableError):
            AuditLog.objects.all().delete()
        with self.assertRaises(ImmutableError):
            AuditLog.objects.all().update(reason='x')
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_actor_name_survives_user_deletion(self):
        self.user.delete()
        self.log.refresh_from_db()
        self.assertIsNone(self.log.actor)
        self.assertEqual(self.log.actor_username, 'u1')


class SanitizeTests(TestCase):
    def test_sensitive_fields_masked(self):
        data = sanitize({'name': 'x', 'password': 'p', 'api_token': 't', 'nested': {'client_secret': 's'}})
        self.assertEqual(data['name'], 'x')
        self.assertEqual(data['password'], '***')
        self.assertEqual(data['api_token'], '***')
        self.assertEqual(data['nested']['client_secret'], '***')

    def test_decimal_and_date_serialisable(self):
        import datetime, decimal
        out = sanitize({'a': decimal.Decimal('1.50'), 'd': datetime.date(2026, 1, 2)})
        self.assertEqual(out, {'a': '1.50', 'd': '2026-01-02'})


class ClientIpBehindProxyTests(TestCase):
    """خلف وكيل عكسي يرى التطبيق عنوان الوكيل (10.0.0.2) لا عنوان العميل. القراءة من اليمين تمنع التزوير."""

    def req(self, xff=None, remote='10.0.0.2'):
        from django.test import RequestFactory
        extra = {'REMOTE_ADDR': remote}
        if xff is not None:
            extra['HTTP_X_FORWARDED_FOR'] = xff
        return RequestFactory().get('/', **extra)

    def ip(self, request, hops):
        from django.test import override_settings
        from .services import client_ip
        with override_settings(PROXY_HOPS=hops):
            return client_ip(request)

    def test_default_does_not_trust_forwarded_header(self):
        self.assertEqual(self.ip(self.req('203.0.113.9'), 0), '10.0.0.2')

    def test_single_proxy_reads_last_entry(self):
        self.assertEqual(self.ip(self.req('203.0.113.9'), 1), '203.0.113.9')

    def test_spoofed_prefix_is_ignored(self):
        # المهاجم أرسل ترويسة بعنوان مزوَّر، والوكيل ألحق العنوان الحقيقي في النهاية
        self.assertEqual(self.ip(self.req('1.2.3.4, 198.51.100.7'), 1), '198.51.100.7')

    def test_two_proxies_read_second_from_right(self):
        self.assertEqual(self.ip(self.req('1.2.3.4, 198.51.100.7, 10.0.0.1'), 2), '198.51.100.7')

    def test_falls_back_when_header_missing_short_or_invalid(self):
        self.assertEqual(self.ip(self.req(None), 1), '10.0.0.2')
        self.assertEqual(self.ip(self.req('203.0.113.9'), 2), '10.0.0.2')          # أقل من عدد الوكلاء
        self.assertEqual(self.ip(self.req('not-an-ip'), 1), '10.0.0.2')
        self.assertEqual(self.ip(self.req('<script>alert(1)</script>'), 1), '10.0.0.2')

    def test_ipv6_supported_and_normalised(self):
        self.assertEqual(self.ip(self.req('2001:DB8::1'), 1), '2001:db8::1')

    def test_audit_entry_records_real_ip(self):
        from django.contrib.auth import get_user_model
        from django.test import override_settings
        user = get_user_model().objects.create_user('ipuser', password='x-Pass-12345')
        with override_settings(PROXY_HOPS=1):
            self.client.force_login(user)
            self.client.get('/', HTTP_X_FORWARDED_FOR='9.9.9.9, 203.0.113.50', REMOTE_ADDR='10.0.0.2')
            from .services import log_action
            entry = log_action(AuditLog.Action.OTHER, entity_type='t.T', request=self.req('1.1.1.1, 203.0.113.50'),
                               actor=user)
        self.assertEqual(entry.ip_address, '203.0.113.50')
