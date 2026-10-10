"""
المساعد الآلي: قائمة الخدمات على واتساب، إنشاء الطلب من الاختيار، والتحويل لفريق الدعم.
"""
from unittest import mock

from django.test import override_settings

from apps.core.models import Notification
from apps.servicedesk.models import ServiceRequest, ServiceType
from apps.suppliers.models import Supplier, SupplierContact

from . import bot, services
from .models import ConversationMessage as M
from .models import SupplierConversation
from .tests_inbox import NUMBER, S, Base, upsert


@override_settings(WHATSAPP_BOT_ENABLED=True)
class BotBase(Base):
    def setUp(self):
        super().setUp()
        self.supplier = Supplier.objects.create(name='شركة الأفق', code='S1')
        SupplierContact.objects.create(supplier=self.supplier, name='م', phone=NUMBER, is_approved=True)
        self.sent = []
        patcher = mock.patch('apps.whatsapp.client.send_text',
                             side_effect=lambda number, text: self.sent.append(text) or {'key': {'id': f'B{len(self.sent)}'}})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.n = 0

    def say(self, text, number=NUMBER):
        self.n += 1
        with self.captureOnCommitCallbacks(execute=True):
            self.post_event(upsert(msg_id=f'IN{self.n}', text=text, number=number))
        return SupplierConversation.objects.get(contact_number=number)

    def types(self):
        return bot.menu_types()


class MenuFlowTests(BotBase):
    def test_first_message_gets_menu_and_stays_out_of_staff_queue(self):
        Notification.objects.all().delete()
        conv = self.say('السلام عليكم')
        self.assertEqual((conv.bot_state, conv.status, conv.unread_count), ('menu', S.PENDING, 0))
        self.assertIsNone(conv.awaiting_reply_since)
        self.assertEqual(len(self.sent), 1)
        self.assertIn('شركة الأفق', self.sent[0])
        for i, t in enumerate(self.types(), 1):
            self.assertIn(f'{i}- {t.name}', self.sent[0])
        self.assertIn('0- التحدث مع فريق الدعم', self.sent[0])
        self.assertEqual(Notification.objects.count(), 0)
        reply = M.objects.get(direction='out')
        self.assertTrue(reply.is_automated)
        self.assertEqual(reply.status, 'sent')

    def test_choose_service_then_details_creates_request_and_closes(self):
        self.say('مرحبا')
        first = self.types()[0]
        conv = self.say('1')
        self.assertEqual((conv.bot_state, conv.bot_service_code), ('collect', first.code))
        self.assertIn(first.name, self.sent[-1])
        Notification.objects.all().delete()
        conv = self.say('أريد معرفة موعد صرف الفاتورة 123')
        req = ServiceRequest.objects.get()
        self.assertEqual((req.service_type, req.supplier, req.source, req.conversation), (first, self.supplier, 'whatsapp', conv))
        self.assertIsNone(req.created_by)
        self.assertIn('الفاتورة 123', req.details)
        self.assertEqual((conv.status, conv.bot_state), (S.CLOSED, ''))
        self.assertIn(req.reference, self.sent[-1])
        self.assertTrue(Notification.objects.filter(link=f'/service-requests/{req.pk}/').exists())

    def test_arabic_indic_digits_are_understood(self):
        self.say('مرحبا')
        self.assertEqual(self.say('٢').bot_service_code, self.types()[1].code)

    def test_new_message_after_request_starts_a_fresh_menu(self):
        self.say('مرحبا')
        self.say('1')
        self.say('تفاصيل')
        conv = self.say('سؤال آخر')
        self.assertEqual((conv.bot_state, conv.status), ('menu', S.PENDING))
        self.assertEqual(sum('اختر الخدمة' in t for t in self.sent), 2)

    def test_hash_returns_to_menu(self):
        self.say('مرحبا')
        self.say('1')
        conv = self.say('#')
        self.assertEqual((conv.bot_state, conv.bot_service_code), ('menu', ''))

    def test_inactive_or_hidden_types_are_not_offered(self):
        ServiceType.objects.filter(code='meeting').update(whatsapp_menu=False)
        ServiceType.objects.filter(code='payment-status').update(is_active=False)
        names = [t.name for t in self.types()]
        self.assertNotIn(ServiceType.objects.get(code='meeting').name, names)
        self.assertNotIn(ServiceType.objects.get(code='payment-status').name, names)


class HandoffTests(BotBase):
    def test_zero_hands_over_to_support_and_notifies_desk(self):
        self.say('مرحبا')
        Notification.objects.all().delete()
        conv = self.say('0')
        self.assertEqual((conv.bot_state, conv.status, conv.unread_count), ('human', S.NEW, 1))
        self.assertIsNotNone(conv.awaiting_reply_since)
        self.assertIn('فريق الدعم', self.sent[-1])
        self.assertEqual(set(Notification.objects.values_list('recipient__username', flat=True)), {'sup', 'agent1', 'agent2'})

    def test_bot_is_silent_after_handoff(self):
        self.say('مرحبا')
        self.say('0')
        count = len(self.sent)
        conv = self.say('هل من رد؟')
        self.assertEqual(len(self.sent), count)
        self.assertEqual((conv.status, conv.unread_count), (S.NEW, 2))

    def test_three_unclear_answers_hand_over(self):
        self.say('مرحبا')
        self.say('ممكن مساعدة')
        self.say('؟؟')
        self.assertIn('لم أفهم', self.sent[-1])
        conv = self.say('طيب')
        self.assertEqual(conv.bot_state, 'human')

    def test_attachment_while_collecting_goes_to_human(self):
        self.say('مرحبا')
        self.say('1')
        payload = upsert(msg_id='DOC1', message={'documentMessage': {'fileName': 'x.pdf', 'mimetype': 'application/pdf'}})
        payload['data']['messageType'] = 'documentMessage'
        with mock.patch('apps.whatsapp.services.schedule_media_fetch'):
            with self.captureOnCommitCallbacks(execute=True):
                self.post_event(payload)
        self.assertEqual(SupplierConversation.objects.get().bot_state, 'human')
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_staff_reply_silences_the_bot(self):
        conv = self.say('مرحبا')
        with self.captureOnCommitCallbacks(execute=True):
            services.send_reply(conv.pk, self.sup, 'أهلًا، كيف أخدمك؟')
        conv.refresh_from_db()
        self.assertEqual(conv.bot_state, 'human')
        count = len(self.sent)
        self.say('أحتاج مساعدة')
        self.assertEqual(len(self.sent), count)

    def test_reopened_conversation_restarts_the_bot(self):
        self.say('مرحبا')
        self.say('0')
        conv = SupplierConversation.objects.get()
        services.set_status(conv.pk, self.sup, S.CLOSED, 'تم')
        conv = self.say('رسالة جديدة')
        self.assertEqual(conv.bot_state, 'menu')


class EligibilityTests(BotBase):
    def test_unknown_number_is_left_to_staff(self):
        conv = self.say('مرحبا', number='966555555555')
        self.assertEqual((conv.bot_state, conv.status, conv.unread_count), ('', S.NEW, 1))
        self.assertEqual(self.sent, [])

    def test_assigned_conversation_is_not_handled(self):
        conv = self.say('مرحبا')
        conv.assigned_agent = self.a1
        conv.bot_state = ''
        conv.save()
        count = len(self.sent)
        self.say('أهلًا')
        self.assertEqual(len(self.sent), count)

    @override_settings(WHATSAPP_BOT_ENABLED=False)
    def test_kill_switch(self):
        conv = self.say('مرحبا')
        self.assertEqual((conv.bot_state, self.sent, conv.status), ('', [], S.NEW))

    def test_no_menu_types_hands_over_immediately(self):
        ServiceType.objects.update(whatsapp_menu=False)
        conv = self.say('مرحبا')
        self.assertEqual((conv.bot_state, conv.status), ('human', S.NEW))

    def test_failure_inside_bot_never_breaks_the_webhook(self):
        with mock.patch('apps.whatsapp.bot._handle', side_effect=RuntimeError('boom')):
            resp = self.post_event(upsert(msg_id='X1', text='مرحبا'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(M.objects.filter(wa_message_id='X1').count(), 1)

    def test_own_messages_never_trigger_the_bot(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.post_event(upsert(msg_id='OUT1', text='رد من الهاتف', from_me=True))
        self.assertEqual(self.sent, [])
