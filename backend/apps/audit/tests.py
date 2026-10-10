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


class ViewAccessTests(TestCase):
    def test_accountant_cannot_view_audit(self):
        from apps.core.models import Role, UserProfile
        role = Role.objects.create(name='acc', role_type=Role.RoleType.ACCOUNTANT)
        u = User.objects.create_user('a1', password='x-Pass-12345')
        UserProfile.objects.create(user=u, role=role)
        self.client.force_login(u)
        self.assertEqual(self.client.get('/audit/').status_code, 302)

    def test_superuser_can_view(self):
        u = User.objects.create_superuser('root', password='x-Pass-12345')
        self.client.force_login(u)
        self.assertEqual(self.client.get('/audit/').status_code, 200)
