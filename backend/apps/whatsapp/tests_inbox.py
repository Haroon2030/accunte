import datetime
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.models import Notification, Role, UserProfile
from apps.suppliers.models import Supplier, SupplierContact

from . import client, services
from .client import WhatsAppError
from .models import ConversationAssignment, ConversationMessage, SLAConfiguration, SupplierConversation
from .services import ConversationError

User = get_user_model()
S = SupplierConversation.Status
M = ConversationMessage
SECRET = 'whsec-test-123'
CFG = dict(WHATSAPP_ENABLED=True, EVOLUTION_API_URL='http://evo.test:8081', EVOLUTION_API_KEY='k', EVOLUTION_INSTANCE='hr',
           WHATSAPP_WEBHOOK_SECRET=SECRET, WHATSAPP_ASYNC_DISPATCH=False, WHATSAPP_DEFAULT_COUNTRY='966',
           WHATSAPP_PUBLIC_BASE_URL='http://app.test')
NUMBER = '966501234567'


def make_user(username, role_type):
    role, _ = Role.objects.get_or_create(role_type=role_type, defaults={'name': f'r-{role_type}', 'is_system_role': True})
    u = User.objects.create_user(username, password='x-Pass-12345')
    UserProfile.objects.create(user=u, role=role)
    return u


def upsert(msg_id='ABC1', text='مرحبا', number=NUMBER, from_me=False, name='شركة الأفق', ts=1760000000, message=None, jid=None):
    return {'event': 'messages.upsert', 'instance': 'hr', 'data': {
        'key': {'remoteJid': jid or f'{number}@s.whatsapp.net', 'fromMe': from_me, 'id': msg_id},
        'pushName': name, 'messageTimestamp': ts, 'messageType': 'conversation',
        'message': message if message is not None else {'conversation': text}}}


@override_settings(**CFG)
class Base(TestCase):
    def setUp(self):
        self.sup = make_user('sup', Role.RoleType.CS_SUPERVISOR)
        self.a1 = make_user('agent1', Role.RoleType.CS_AGENT)
        self.a2 = make_user('agent2', Role.RoleType.CS_AGENT)
        self.acc = make_user('acc', Role.RoleType.ACCOUNTANT)
        self.cfo = make_user('cfo', Role.RoleType.CFO)

    def post_event(self, payload, secret=SECRET):
        return self.client.post(reverse('whatsapp:webhook', args=[secret]), json.dumps(payload),
                                content_type='application/json')

    def conv(self, **kw):
        c = SupplierConversation.objects.create(contact_number=kw.pop('number', NUMBER), **kw)
        return c


class WebhookAuthTests(Base):
    def test_wrong_or_missing_secret_is_404_and_stores_nothing(self):
        for secret in ('wrong', SECRET[:-1], ''):
            if not secret:
                continue
            self.assertEqual(self.post_event(upsert(), secret).status_code, 404)
        self.assertEqual(M.objects.count(), 0)

    @override_settings(WHATSAPP_WEBHOOK_SECRET='')
    def test_unset_secret_rejects_everything(self):
        self.assertEqual(self.client.post('/whatsapp/webhook/anything/', '{}', content_type='application/json').status_code, 404)

    @override_settings(WHATSAPP_ENABLED=False)
    def test_disabled_rejects(self):
        self.assertEqual(self.post_event(upsert()).status_code, 404)

    def test_get_not_allowed_and_bad_json(self):
        self.assertEqual(self.client.get(reverse('whatsapp:webhook', args=[SECRET])).status_code, 405)
        r = self.client.post(reverse('whatsapp:webhook', args=[SECRET]), 'not json', content_type='application/json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post(reverse('whatsapp:webhook', args=[SECRET]), '[1,2]', content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_other_instance_ignored(self):
        p = upsert()
        p['instance'] = 'other'
        r = self.post_event(p)
        self.assertEqual(r.json()['processed'], 0)
        self.assertEqual(M.objects.count(), 0)

    def test_no_csrf_needed(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        r = c.post(reverse('whatsapp:webhook', args=[SECRET]), json.dumps(upsert()), content_type='application/json')
        self.assertEqual(r.status_code, 200)


class IdempotencyTests(Base):
    def test_duplicate_webhook_payload_creates_one_message(self):
        for _ in range(3):
            self.assertEqual(self.post_event(upsert('SAME-ID')).status_code, 200)
        self.assertEqual(M.objects.count(), 1)
        c = SupplierConversation.objects.get()
        self.assertEqual(c.unread_count, 1)          # لا يتضاعف العداد مع التكرار
        self.assertEqual(services.ingest_message(upsert('SAME-ID')['data']), 'duplicate')

    def test_unique_constraint_blocks_duplicates_at_db_level(self):
        c = self.conv()
        M.objects.create(conversation=c, direction='in', wa_message_id='X1', body='a')
        with self.assertRaises(IntegrityError), transaction.atomic():
            M.objects.create(conversation=c, direction='in', wa_message_id='X1', body='b')
        M.objects.create(conversation=c, direction='out', wa_message_id='', body='1')   # الفارغ لا يتعارض
        M.objects.create(conversation=c, direction='out', wa_message_id='', body='2')

    def test_batch_payload_with_repeated_ids(self):
        p = upsert('B1')
        p['data'] = [p['data'], upsert('B1')['data'], upsert('B2', text='ثانية')['data']]
        self.post_event(p)
        self.assertEqual(M.objects.count(), 2)

    def test_distinct_messages_same_conversation(self):
        self.post_event(upsert('M1'))
        self.post_event(upsert('M2', text='رسالة ثانية'))
        self.assertEqual(SupplierConversation.objects.count(), 1)
        self.assertEqual(SupplierConversation.objects.get().unread_count, 2)


class ContentExtractionTests(Base):
    def test_kinds(self):
        cases = [
            ({'conversation': 'نص'}, ('text', 'نص', '')),
            ({'extendedTextMessage': {'text': 'رابط'}}, ('text', 'رابط', '')),
            ({'imageMessage': {'caption': 'فاتورة'}}, ('image', 'فاتورة', '')),
            ({'documentMessage': {'fileName': 'a.pdf', 'caption': 'كشف'}}, ('document', 'كشف', 'a.pdf')),
            ({'audioMessage': {}}, ('audio', '', '')),
            ({'ephemeralMessage': {'message': {'conversation': 'مؤقتة'}}}, ('text', 'مؤقتة', '')),
        ]
        for message, expected in cases:
            self.assertEqual(tuple(map(str, services.extract_content(message))), expected)

    def test_reactions_and_protocol_ignored(self):
        self.assertIsNone(services.extract_content({'reactionMessage': {'text': '👍'}}))
        self.assertIsNone(services.extract_content({'protocolMessage': {}}))
        self.assertEqual(services.ingest_message(upsert(message={'reactionMessage': {}})['data']), 'ignored')

    def test_groups_status_and_lid_ignored(self):
        for jid in ('12345-67890@g.us', 'status@broadcast', '999@newsletter', '555@lid'):
            self.assertEqual(services.ingest_message(upsert('G' + jid, jid=jid)['data']), 'ignored', jid)
        self.assertEqual(M.objects.count(), 0)

    def test_lid_with_alt_number_is_used(self):
        data = upsert('L1')['data']
        data['key'] = {'remoteJid': '555@lid', 'remoteJidAlt': f'{NUMBER}@s.whatsapp.net', 'id': 'L1', 'fromMe': False}
        self.assertEqual(services.ingest_message(data), 'created')
        self.assertEqual(SupplierConversation.objects.get().contact_number, NUMBER)

    def test_timestamp_variants(self):
        for i, ts in enumerate((1760000000, '1760000000', 1760000000000, {'low': 1760000000}, None, 'bad')):
            d = upsert(f'T{i}', ts=ts)['data']
            self.assertEqual(services.ingest_message(d), 'created')
        self.assertEqual(M.objects.count(), 6)


class SupplierMatchingTests(Base):
    def test_known_contact_links_supplier(self):
        s = Supplier.objects.create(name='مورد', code='S1')
        SupplierContact.objects.create(supplier=s, phone=NUMBER, name='أحمد')
        self.post_event(upsert())
        c = SupplierConversation.objects.get()
        self.assertEqual(c.supplier, s)

    def test_unknown_and_ambiguous_numbers_stay_unlinked(self):
        self.post_event(upsert('U1', number='966500000001'))
        s1, s2 = Supplier.objects.create(name='a', code='1'), Supplier.objects.create(name='b', code='2')
        SupplierContact.objects.create(supplier=s1, phone='966500000002')
        SupplierContact.objects.create(supplier=s2, phone='966500000002')
        self.post_event(upsert('U2', number='966500000002'))
        self.assertTrue(all(c.supplier is None for c in SupplierConversation.objects.all()))

    def test_unapproved_contact_not_matched(self):
        s = Supplier.objects.create(name='مورد', code='S1')
        SupplierContact.objects.create(supplier=s, phone=NUMBER, is_approved=False)
        self.post_event(upsert())
        self.assertIsNone(SupplierConversation.objects.get().supplier)


class LifecycleAndSlaTests(Base):
    def test_new_conversation_notifies_desk_and_is_new(self):
        self.post_event(upsert())
        c = SupplierConversation.objects.get()
        self.assertEqual((c.status, c.unread_count), (S.NEW, 1))
        self.assertIsNotNone(c.awaiting_reply_since)
        recipients = set(Notification.objects.values_list('recipient__username', flat=True))
        self.assertEqual(recipients, {'sup', 'agent1', 'agent2'})

    def test_closed_conversation_reopens_on_new_inbound(self):
        c = self.conv(status=S.CLOSED, assigned_agent=self.a1)
        services.set_status  # noqa
        self.post_event(upsert('R1'))
        c.refresh_from_db()
        self.assertEqual(c.status, S.OPEN)         # لها موظف: تعود مفتوحة
        c2 = self.conv(number='966500000009', status=S.CLOSED)
        self.post_event(upsert('R2', number='966500000009'))
        c2.refresh_from_db()
        self.assertEqual(c2.status, S.NEW)

    def test_customer_reply_moves_pending_back_to_open(self):
        c = self.conv(status=S.PENDING, assigned_agent=self.a1)
        self.post_event(upsert('P1'))
        c.refresh_from_db()
        self.assertEqual(c.status, S.OPEN)

    def test_assigned_agent_notified_once_on_first_unread(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        self.post_event(upsert('N1'))
        self.post_event(upsert('N2'))
        self.assertEqual(Notification.objects.filter(recipient=self.a1).count(), 1)

    def test_unanswered_overdue_flag_follows_sla(self):
        SLAConfiguration.objects.update_or_create(name='default', defaults={'first_response_minutes': 30})
        c = self.conv(status=S.OPEN, assigned_agent=self.a1,
                      awaiting_reply_since=timezone.now() - datetime.timedelta(minutes=45))
        self.assertTrue(c.is_unanswered_overdue)
        c.awaiting_reply_since = timezone.now() - datetime.timedelta(minutes=10)
        self.assertFalse(c.is_unanswered_overdue)
        c.awaiting_reply_since = timezone.now() - datetime.timedelta(minutes=90)
        c.status = S.CLOSED
        self.assertFalse(c.is_unanswered_overdue)

    def test_reply_from_phone_closes_awaiting_and_records_response_time(self):
        self.post_event(upsert('I1', ts=1760000000))
        self.post_event(upsert('O1', from_me=True, text='تم', ts=1760000300))
        c = SupplierConversation.objects.get()
        self.assertIsNone(c.awaiting_reply_since)
        self.assertEqual(c.last_response_seconds, 300)
        self.assertEqual(M.objects.get(wa_message_id='O1').response_seconds, 300)

    def test_status_update_never_downgrades(self):
        c = self.conv()
        M.objects.create(conversation=c, direction='out', wa_message_id='W1', body='x', status='sent')
        upd = lambda st: {'event': 'messages.update', 'instance': 'hr', 'data': {'keyId': 'W1', 'status': st}}
        self.post_event(upd('READ'))
        self.assertEqual(M.objects.get().status, 'read')
        self.post_event(upd('DELIVERY_ACK'))
        self.assertEqual(M.objects.get().status, 'read')
        self.post_event(upd('SOMETHING'))
        self.assertEqual(M.objects.get().status, 'read')


class ClaimAndConcurrencyTests(Base):
    def test_only_one_agent_wins_a_claim(self):
        c = self.conv(status=S.NEW)
        services.claim(c.pk, self.a1)
        with self.assertRaises(ConversationError) as cm:
            services.claim(c.pk, self.a2)
        self.assertIn('موظف آخر', str(cm.exception))
        c.refresh_from_db()
        self.assertEqual((c.assigned_agent, c.status), (self.a1, S.OPEN))
        self.assertEqual(c.assignments.filter(is_active=True).count(), 1)

    def test_claim_closed_rejected_and_accountant_forbidden(self):
        closed = self.conv(status=S.CLOSED)
        with self.assertRaises(ConversationError):
            services.claim(closed.pk, self.a1)
        c = self.conv(number='966500000005')
        with self.assertRaises(ConversationError):
            services.claim(c.pk, self.acc)

    def test_assign_uses_optimistic_version(self):
        c = self.conv(status=S.NEW)
        v = c.version
        services.assign(c.pk, self.a1, self.sup, expected_version=v)
        with self.assertRaises(ConversationError) as cm:     # نسخة قديمة
            services.assign(c.pk, self.a2, self.sup, expected_version=v)
        self.assertIn('تغيّرت', str(cm.exception))
        c.refresh_from_db()
        self.assertEqual(c.assigned_agent, self.a1)

    def test_agent_cannot_assign_but_supervisor_can_reassign(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        with self.assertRaises(ConversationError):
            services.assign(c.pk, self.a2, self.a1)
        services.assign(c.pk, self.a2, self.sup)
        c.refresh_from_db()
        self.assertEqual(c.assigned_agent, self.a2)
        self.assertEqual(c.assignments.count(), 1)
        self.assertEqual(ConversationAssignment.objects.filter(conversation=c, is_active=True).count(), 1)

    def test_agent_cannot_touch_peers_conversation(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        for fn in (lambda: services.set_status(c.pk, self.a2, S.PENDING),
                   lambda: services.release(c.pk, self.a2),
                   lambda: services.send_reply(c.pk, self.a2, 'مرحبا')):
            with self.assertRaises(ConversationError):
                fn()

    def test_escalation_requires_reason_and_notifies_supervisors(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        with self.assertRaises(ConversationError):
            services.set_status(c.pk, self.a1, S.ESCALATED, '')
        services.set_status(c.pk, self.a1, S.ESCALATED, 'مبلغ كبير')
        c.refresh_from_db()
        self.assertEqual((c.status, c.escalation_reason), (S.ESCALATED, 'مبلغ كبير'))
        self.assertTrue(Notification.objects.filter(recipient=self.sup, title__contains='مصعَّدة').exists())
        log = AuditLog.objects.get(entity_type='whatsapp.Conversation', action=AuditLog.Action.STATUS_CHANGE)
        self.assertEqual((log.actor, log.new_state['status']), (self.a1, 'escalated'))

    def test_release_returns_to_new(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        services.release(c.pk, self.a1)
        c.refresh_from_db()
        self.assertEqual((c.assigned_agent, c.status), (None, S.NEW))

    def test_typing_lock_blocks_other_agent_but_not_supervisor(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        services.ping_typing(c.pk, self.a2)
        with self.assertRaises(ConversationError) as cm:
            services.send_reply(c.pk, self.a1, 'x')
        self.assertIn('يكتب', str(cm.exception))
        with mock.patch('apps.whatsapp.client.send_text', return_value={'key': {'id': 'S1'}}):
            with self.captureOnCommitCallbacks(execute=True):
                services.send_reply(c.pk, self.sup, 'رد المشرف')


class SendTests(Base):
    def test_send_marks_sent_and_stores_wa_id_and_response_time(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1,
                      awaiting_reply_since=timezone.now() - datetime.timedelta(minutes=5), unread_count=2)
        with mock.patch('apps.whatsapp.client.send_text', return_value={'key': {'id': 'OUT-1'}}) as sent:
            with self.captureOnCommitCallbacks(execute=True):
                msg = services.send_reply(c.pk, self.a1, '  تم التحويل  ')
        sent.assert_called_once_with(NUMBER, 'تم التحويل')
        msg.refresh_from_db()
        self.assertEqual((msg.status, msg.wa_message_id, msg.sent_by), ('sent', 'OUT-1', self.a1))
        self.assertTrue(299 <= msg.response_seconds <= 320)
        c.refresh_from_db()
        self.assertEqual((c.unread_count, c.awaiting_reply_since), (0, None))

    def test_failure_marks_failed_and_resend_works(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        with mock.patch('apps.whatsapp.client.send_text', side_effect=WhatsAppError('تعذر الاتصال')):
            with self.captureOnCommitCallbacks(execute=True):
                msg = services.send_reply(c.pk, self.a1, 'مرحبا')
        msg.refresh_from_db()
        self.assertEqual((msg.status, msg.error), ('failed', 'تعذر الاتصال'))
        with mock.patch('apps.whatsapp.client.send_text', return_value={'key': {'id': 'OUT-2'}}) as sent:
            services.resend(msg.pk, self.a1)
        self.assertEqual(sent.call_count, 1)
        msg.refresh_from_db()
        self.assertEqual(msg.status, 'sent')
        with mock.patch('apps.whatsapp.client.send_text') as again:
            services.deliver(msg.pk)                 # لا إرسال ثانٍ لرسالة أُرسلت
        again.assert_not_called()

    def test_validation(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        for text in ('', '   ', 'x' * 4001):
            with self.assertRaises(ConversationError):
                services.send_reply(c.pk, self.a1, text)
        closed = self.conv(number='966500000006', status=S.CLOSED, assigned_agent=self.a1)
        with self.assertRaises(ConversationError):
            services.send_reply(closed.pk, self.a1, 'مرحبا')

    def test_supervisor_reply_on_unassigned_auto_claims(self):
        c = self.conv(status=S.NEW)
        with mock.patch('apps.whatsapp.client.send_text', return_value={'key': {'id': 'S-1'}}):
            with self.captureOnCommitCallbacks(execute=True):
                services.send_reply(c.pk, self.sup, 'أهلا')
        c.refresh_from_db()
        self.assertEqual((c.assigned_agent, c.status), (self.sup, S.OPEN))

    def test_agent_cannot_reply_on_unassigned(self):
        c = self.conv(status=S.NEW)
        with self.assertRaises(ConversationError):
            services.send_reply(c.pk, self.a1, 'أهلا')

    def test_webhook_echo_arriving_before_id_saved_is_merged(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        with self.captureOnCommitCallbacks(execute=False):
            msg = services.send_reply(c.pk, self.a1, 'مرحبا')
        # صدى الـ webhook يصل أولًا بنفس المعرّف
        self.post_event(upsert('ECHO-1', from_me=True, text='مرحبا'))
        with mock.patch('apps.whatsapp.client.send_text', return_value={'key': {'id': 'ECHO-1'}}):
            services.deliver(msg.pk)
        rows = M.objects.filter(wa_message_id='ECHO-1')
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().sent_by, self.a1)
        self.assertEqual(M.objects.filter(conversation=c).count(), 1)

    @override_settings(WHATSAPP_ASYNC_DISPATCH=True)
    def test_async_dispatch_starts_background_thread(self):
        c = self.conv(status=S.OPEN, assigned_agent=self.a1)
        with mock.patch('apps.whatsapp.services._dispatch_async') as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                msg = services.send_reply(c.pk, self.a1, 'مرحبا')
        dispatch.assert_called_once_with(msg.pk)
        msg.refresh_from_db()
        self.assertEqual(msg.status, 'pending')


class InboxViewTests(Base):
    def setUp(self):
        super().setUp()
        self.new = self.conv(status=S.NEW, display_name='جديد', last_message_at=timezone.now())
        self.mine = self.conv(number='966500000011', status=S.OPEN, assigned_agent=self.a1, display_name='لي',
                              last_message_at=timezone.now())
        self.peer = self.conv(number='966500000012', status=S.OPEN, assigned_agent=self.a2, display_name='زميلي',
                              last_message_at=timezone.now())
        self.esc = self.conv(number='966500000013', status=S.ESCALATED, display_name='مصعد', last_message_at=timezone.now())
        self.closed = self.conv(number='966500000014', status=S.CLOSED, display_name='مغلق', last_message_at=timezone.now())

    def names(self, resp):
        return {c.display_name for c in resp.context['page_obj']}

    def test_tabs(self):
        self.client.force_login(self.a1)
        url = reverse('whatsapp_inbox:inbox')
        self.assertEqual(self.names(self.client.get(url, {'tab': 'new'})), {'جديد'})
        self.assertEqual(self.names(self.client.get(url, {'tab': 'mine'})), {'لي'})
        self.assertEqual(self.names(self.client.get(url, {'tab': 'unassigned'})), {'جديد', 'مصعد'})
        self.assertEqual(self.names(self.client.get(url, {'tab': 'escalated'})), {'مصعد'})
        self.assertEqual(self.names(self.client.get(url, {'tab': 'closed'})), {'مغلق'})
        self.assertEqual(len(self.names(self.client.get(url, {'tab': 'all'}))), 5)
        counts = self.client.get(url).context['counts']
        self.assertEqual((counts['new'], counts['mine'], counts['closed']), (1, 1, 1))

    def test_late_filter(self):
        SupplierConversation.objects.filter(pk=self.new.pk).update(
            awaiting_reply_since=timezone.now() - datetime.timedelta(hours=2))
        self.client.force_login(self.sup)
        r = self.client.get(reverse('whatsapp_inbox:inbox'), {'tab': 'all', 'late': '1'})
        self.assertEqual(self.names(r), {'جديد'})

    def test_htmx_returns_partial(self):
        self.client.force_login(self.a1)
        full = self.client.get(reverse('whatsapp_inbox:inbox')).content.decode()
        part = self.client.get(reverse('whatsapp_inbox:inbox'), HTTP_HX_REQUEST='true').content.decode()
        self.assertIn('<html', full)
        self.assertNotIn('<html', part)

    def test_access_by_role(self):
        url = reverse('whatsapp_inbox:inbox')
        for user, code in ((self.a1, 200), (self.sup, 200), (self.cfo, 200), (self.acc, 302)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, code, user.username)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_open_marks_read_only_for_who_can_act(self):
        SupplierConversation.objects.filter(pk=self.mine.pk).update(unread_count=3)
        self.client.force_login(self.a2)       # ليست محادثته: لا تُصفَّر
        self.client.get(reverse('whatsapp_inbox:conversation', args=[self.mine.pk]))
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.unread_count, 3)
        self.client.force_login(self.a1)
        self.client.get(reverse('whatsapp_inbox:conversation', args=[self.mine.pk]))
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.unread_count, 0)

    def test_thread_page_and_polling_partial(self):
        M.objects.create(conversation=self.mine, direction='in', wa_message_id='V1', body='نص الرسالة')
        self.client.force_login(self.a1)
        url = reverse('whatsapp_inbox:conversation', args=[self.mine.pk])
        self.assertIn('نص الرسالة', self.client.get(url).content.decode())
        part = self.client.get(url, HTTP_HX_REQUEST='true').content.decode()
        self.assertIn('نص الرسالة', part)
        self.assertNotIn('<html', part)

    def test_message_body_is_escaped(self):
        M.objects.create(conversation=self.mine, direction='in', wa_message_id='X', body='<script>alert(1)</script>')
        self.client.force_login(self.a1)
        html = self.client.get(reverse('whatsapp_inbox:conversation', args=[self.mine.pk])).content.decode()
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_http_claim_send_and_peer_blocked(self):
        self.client.force_login(self.a1)
        self.client.post(reverse('whatsapp_inbox:claim', args=[self.new.pk]))
        self.new.refresh_from_db()
        self.assertEqual(self.new.assigned_agent, self.a1)
        self.client.force_login(self.a2)
        r = self.client.post(reverse('whatsapp_inbox:claim', args=[self.new.pk]), follow=True)
        self.assertIn('موظف آخر', r.content.decode())
        self.client.post(reverse('whatsapp_inbox:send', args=[self.new.pk]), {'text': 'تسلل'})
        self.assertEqual(M.objects.filter(conversation=self.new, direction='out').count(), 0)

    def test_link_supplier_by_code(self):
        s = Supplier.objects.create(name='مورد', code='SUP-9')
        self.client.force_login(self.a1)
        self.client.post(reverse('whatsapp_inbox:link_supplier', args=[self.mine.pk]), {'supplier_code': 'SUP-9'})
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.supplier, s)
        r = self.client.post(reverse('whatsapp_inbox:link_supplier', args=[self.mine.pk]), {'supplier_code': 'NOPE'}, follow=True)
        self.assertIn('لا يوجد مورد', r.content.decode())

    def test_state_changing_views_reject_get(self):
        self.client.force_login(self.sup)
        for name in ('claim', 'release', 'assign', 'set_status', 'send', 'typing', 'link_supplier', 'link_case'):
            self.assertEqual(self.client.get(reverse(f'whatsapp_inbox:{name}', args=[self.new.pk])).status_code, 405, name)


class WebhookSetupTests(Base):
    def test_setup_posts_secret_url_without_leaking_it(self):
        self.client.force_login(self.sup)
        with mock.patch('apps.whatsapp.client.set_webhook') as sw:
            r = self.client.post(reverse('whatsapp:setup_webhook'))
        self.assertEqual(r.status_code, 200)
        sw.assert_called_once_with(f'http://app.test/whatsapp/webhook/{SECRET}/')
        self.assertNotIn(SECRET, r.content.decode())
        page = self.client.get(reverse('whatsapp:connect')).content.decode()
        self.assertNotIn(SECRET, page)

    @override_settings(WHATSAPP_PUBLIC_BASE_URL='')
    def test_setup_requires_public_url(self):
        self.client.force_login(self.sup)
        self.assertEqual(self.client.post(reverse('whatsapp:setup_webhook')).status_code, 400)

    def test_setup_forbidden_for_agents(self):
        self.client.force_login(self.a1)
        self.assertEqual(self.client.post(reverse('whatsapp:setup_webhook')).status_code, 302)

    def test_set_webhook_client_payload(self):
        captured = {}

        def fake(method, path, body=None):
            captured.update(method=method, path=path, body=body)
            return {}
        with mock.patch('apps.whatsapp.client._request', fake):
            client.set_webhook('http://app.test/x/')
        self.assertEqual((captured['method'], captured['path']), ('POST', '/webhook/set/hr'))
        w = captured['body']['webhook']
        self.assertTrue(w['enabled'])
        self.assertIn('MESSAGES_UPSERT', w['events'])
