"""
دردشة بوابة الموردين: نفس المساعد الآلي ونفس صندوق الدعم، بلا إرسال عبر واتساب.
"""
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Notification, Role
from apps.suppliers.models import Supplier
from apps.whatsapp import services as chat
from apps.whatsapp.models import ConversationMessage as M
from apps.whatsapp.models import SupplierConversation

from .models import ServiceRequest, ServiceType
from .tests_portal import make_user

RT = Role.RoleType
C = SupplierConversation.Status


@override_settings(WHATSAPP_ENABLED=False, WHATSAPP_BOT_ENABLED=True, GROQ_API_KEY='', WHATSAPP_SUPPORT_NUMBER='')
class ChatBase(TestCase):
    def setUp(self):
        cache.clear()
        self.s1 = Supplier.objects.create(name='شركة الأفق', code='CH1')
        self.s2 = Supplier.objects.create(name='شركة النور', code='CH2')
        self.vendor = make_user('vendor1', RT.SUPPLIER, self.s1)
        self.other = make_user('vendor2', RT.SUPPLIER, self.s2)
        self.sup = make_user('sup', RT.CS_SUPERVISOR)
        self.acc = make_user('acc', RT.ACCOUNTANT)
        self.cfo = make_user('cfo', RT.CFO)
        self.client.force_login(self.vendor)
        patcher = mock.patch('apps.whatsapp.client.send_text')
        self.wa = patcher.start()
        self.addCleanup(patcher.stop)

    def say(self, text, user=None):
        if user is not None:
            self.client.force_login(user)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('portal:chat_send'), {'text': text, 'after': '0'})

    def texts(self):
        self.client.force_login(self.vendor)
        return [m['text'] for m in self.client.get(reverse('portal:chat_poll')).json()['messages']]

    def conv(self):
        return SupplierConversation.objects.get(contact_number=f'portal:{self.s1.pk}')


class PageAndCardTests(ChatBase):
    def test_home_has_live_chat_card_and_no_whatsapp_card_without_number(self):
        html = self.client.get(reverse('portal:home')).content.decode()
        self.assertIn('دردشة مباشرة مع الدعم', html)
        self.assertIn(reverse('portal:chat'), html)
        self.assertNotIn('wa.me', html)

    @override_settings(WHATSAPP_SUPPORT_NUMBER='966501234567')
    def test_whatsapp_card_is_a_secondary_option_when_number_exists(self):
        html = self.client.get(reverse('portal:home')).content.decode()
        self.assertIn(reverse('portal:chat'), html)
        self.assertIn('https://wa.me/966501234567', html)

    def test_chat_page_renders_for_supplier_only(self):
        self.assertEqual(self.client.get(reverse('portal:chat')).status_code, 200)
        self.client.force_login(self.sup)
        for name in ('portal:chat', 'portal:chat_poll'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302, name)
        self.assertEqual(self.client.post(reverse('portal:chat_send'), {'text': 'x'}).status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('portal:chat')).status_code, 302)

    def test_unlinked_supplier_cannot_chat(self):
        self.client.force_login(make_user('lone', RT.SUPPLIER))
        self.assertEqual(self.client.get(reverse('portal:chat')).status_code, 403)


class BotInPortalChatTests(ChatBase):
    def test_first_message_gets_the_menu_without_whatsapp(self):
        Notification.objects.all().delete()
        resp = self.say('السلام عليكم')
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual([m['mine'] for m in data['messages']], [True, False])
        self.assertEqual(data['messages'][1]['who'], 'المساعد الآلي')
        self.assertIn('اختر الخدمة', data['messages'][1]['text'])
        self.assertEqual(self.conv().channel, 'portal')
        self.assertEqual((self.conv().status, self.conv().bot_state), (C.PENDING, 'menu'))
        self.wa.assert_not_called()
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(M.objects.get(direction='out').status, 'sent')

    def test_choosing_a_service_creates_a_portal_request_linked_to_the_chat(self):
        self.say('مرحبا')
        self.say('1')
        self.say('أحتاج مطابقة حساب الربع الأول')
        req = ServiceRequest.objects.get()
        first = ServiceType.objects.filter(is_active=True, whatsapp_menu=True).order_by('sort_order', 'name').first()
        self.assertEqual((req.supplier, req.source, req.service_type, req.conversation), (self.s1, 'portal', first, self.conv()))
        self.assertIn('دردشة البوابة', req.subject)
        self.assertIn(req.reference, self.texts()[-1])
        self.assertEqual(self.conv().status, C.CLOSED)
        self.wa.assert_not_called()

    def test_zero_hands_over_to_support_and_staff_reply_reaches_the_supplier(self):
        self.say('مرحبا')
        Notification.objects.all().delete()
        self.say('0')
        conv = self.conv()
        self.assertEqual((conv.bot_state, conv.status, conv.unread_count), ('human', C.NEW, 1))
        self.assertTrue(Notification.objects.filter(recipient=self.sup).exists())
        with self.captureOnCommitCallbacks(execute=True):
            chat.send_reply(conv.pk, self.sup, 'أهلًا بك، كيف نساعدك؟')
        self.client.force_login(self.vendor)
        last = self.client.get(reverse('portal:chat_poll')).json()['messages'][-1]
        self.assertEqual((last['text'], last['who'], last['mine']), ('أهلًا بك، كيف نساعدك؟', 'فريق الدعم', False))
        self.wa.assert_not_called()                             # لا واتساب لدردشة البوابة

    def test_staff_sees_the_chat_in_the_inbox_with_its_label(self):
        self.say('مرحبا')
        self.say('0')
        self.client.force_login(self.sup)
        html = self.client.get(reverse('whatsapp_inbox:inbox')).content.decode()
        self.assertIn('دردشة بوابة الموردين', html)
        self.assertIn('شركة الأفق', html)
        page = self.client.get(reverse('whatsapp_inbox:conversation', args=[self.conv().pk])).content.decode()
        self.assertIn('دردشة بوابة الموردين', page)

    def test_free_text_uses_the_ai_router(self):
        pay = ServiceType.objects.get(code='payment-status')
        with mock.patch('apps.whatsapp.ai.classify', return_value={'action': 'service', 'type': pay, 'summary': 'استفسار صرف'}):
            self.say('متى يصرف مبلغ فاتورتنا رقم 77؟')
        req = ServiceRequest.objects.get()
        self.assertEqual((req.service_type, req.source, req.subject), (pay, 'portal', 'استفسار صرف'))

    def test_bot_disabled_sends_straight_to_staff(self):
        with override_settings(WHATSAPP_BOT_ENABLED=False):
            self.say('أحتاج مساعدة')
        conv = self.conv()
        self.assertEqual((conv.bot_state, conv.status, conv.unread_count), ('', C.NEW, 1))
        self.assertTrue(Notification.objects.filter(recipient=self.sup).exists())
        self.assertEqual(M.objects.filter(direction='out').count(), 0)

    def test_new_message_after_a_request_starts_a_fresh_menu(self):
        self.say('مرحبا')
        self.say('1')
        self.say('تفاصيل الطلب')
        self.say('سؤال آخر')
        self.assertEqual((self.conv().bot_state, self.conv().status), ('menu', C.PENDING))


class ChatSecurityTests(ChatBase):
    def test_validation(self):
        for text in ('', '   ', 'ا' * 2001):
            resp = self.say(text)
            self.assertEqual(resp.status_code, 400, len(text))
            self.assertFalse(resp.json()['ok'])
        self.assertEqual(M.objects.count(), 0)

    def test_each_supplier_sees_only_its_own_chat(self):
        self.say('رسالة الأفق السرية')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('portal:chat_poll')).json()['messages'], [])
        self.say('رسالة النور', user=self.other)
        self.assertNotIn('رسالة الأفق السرية', [m['text'] for m in self.client.get(reverse('portal:chat_poll')).json()['messages']])
        self.assertEqual(SupplierConversation.objects.count(), 2)

    def test_poll_returns_only_newer_messages_and_is_never_cached(self):
        self.say('مرحبا')
        resp = self.client.get(reverse('portal:chat_poll'))
        ids = [m['id'] for m in resp.json()['messages']]
        self.assertEqual(resp['Cache-Control'], 'no-store')
        newer = self.client.get(reverse('portal:chat_poll'), {'after': ids[0]}).json()['messages']
        self.assertEqual([m['id'] for m in newer], ids[1:])
        self.assertEqual(self.client.get(reverse('portal:chat_poll'), {'after': ids[-1]}).json()['messages'], [])

    def test_chat_page_escapes_message_text(self):
        self.say('<script>alert(1)</script>')
        html = self.client.get(reverse('portal:chat')).content.decode()
        self.assertNotIn('<script>alert(1)</script>', html)

    def test_linking_a_portal_chat_to_a_supplier_is_refused(self):
        self.say('مرحبا')
        with self.assertRaises(chat.ConversationError):
            chat.link_supplier(self.conv().pk, make_user('adm', RT.ADMIN), self.s2)
        with self.assertRaises(chat.ConversationError):
            chat.create_supplier_from_conversation(self.conv().pk, make_user('adm2', RT.ADMIN), 'x')

    def test_get_not_allowed_on_send(self):
        self.assertEqual(self.client.get(reverse('portal:chat_send')).status_code, 405)
