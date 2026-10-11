"""
فهم الرسائل الحرة عبر Groq: التحقق من المخرجات، الفشل الآمن، والتوجيه داخل المساعد الآلي.
"""
import json
import urllib.error
from unittest import mock

from django.test import TestCase, override_settings

from apps.servicedesk.models import ServiceRequest, ServiceType

from . import ai
from .models import SupplierConversation
from .tests_bot import BotBase
from .tests_inbox import S


def fake_response(content):
    resp = mock.MagicMock()
    resp.read.return_value = json.dumps({'choices': [{'message': {'content': content}}]}).encode()
    resp.__enter__.return_value = resp
    return resp


class ClassifyTests(TestCase):
    def setUp(self):
        self.types = list(ServiceType.objects.filter(code__in=['payment-status', 'meeting']).order_by('code'))
        self.pay = ServiceType.objects.get(code='payment-status')

    def classify(self, content=None, **kw):
        with override_settings(GROQ_API_KEY='gsk_test', GROQ_MODEL='m', GROQ_TIMEOUT=3):
            with mock.patch('urllib.request.urlopen', return_value=fake_response(content), **kw) as op:
                return ai.classify('متى يصرف مبلغ فاتورتنا؟', self.types), op

    def test_valid_service(self):
        result, op = self.classify(json.dumps({'action': 'service', 'service': 'payment-status', 'summary': 'استفسار صرف'}))
        self.assertEqual(result, {'action': 'service', 'type': self.pay, 'summary': 'استفسار صرف'})
        req = op.call_args[0][0]
        self.assertEqual(req.get_header('Authorization'), 'Bearer gsk_test')
        body = json.loads(req.data)
        self.assertEqual((body['model'], body['temperature'], body['response_format']), ('m', 0, {'type': 'json_object'}))
        self.assertIn('payment-status', body['messages'][1]['content'])

    def test_unknown_service_code_is_rejected(self):
        result, _ = self.classify(json.dumps({'action': 'service', 'service': 'drop-table', 'summary': 'x'}))
        self.assertIsNone(result)

    def test_human_and_unclear_pass_through(self):
        for action in ('human', 'unclear'):
            result, _ = self.classify(json.dumps({'action': action}))
            self.assertEqual((result['action'], result['type']), (action, None))

    def test_garbage_output_is_none(self):
        for content in ('not json', '[]', '{"action": "delete"}', '{"action": "service"}'):
            self.assertIsNone(self.classify(content)[0], content)

    def test_network_failure_is_none_and_never_leaks_key(self):
        with override_settings(GROQ_API_KEY='gsk_secret_key'):
            with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('down')):
                with self.assertLogs('apps.whatsapp.ai', 'WARNING') as logs:
                    self.assertIsNone(ai.classify('رسالة طويلة بما يكفي', self.types))
        self.assertNotIn('gsk_secret_key', ''.join(logs.output))

    def test_disabled_without_key_makes_no_request(self):
        with override_settings(GROQ_API_KEY=''):
            with mock.patch('urllib.request.urlopen') as op:
                self.assertIsNone(ai.classify('رسالة طويلة بما يكفي', self.types))
        op.assert_not_called()

    def test_input_is_truncated(self):
        with override_settings(GROQ_API_KEY='k'):
            with mock.patch('urllib.request.urlopen', return_value=fake_response('{"action":"unclear"}')) as op:
                ai.classify('ا' * 5000, self.types)
        user = json.loads(op.call_args[0][0].data)['messages'][1]['content']
        self.assertLess(len(user), ai.MAX_INPUT + 800)




class BotRoutingTests(BotBase):
    def route(self, result, text='متى يصرف مبلغ الفاتورة رقم 55؟'):
        with mock.patch('apps.whatsapp.ai.classify', return_value=result) as cl:
            conv = self.say(text)
        return conv, cl

    def pay(self):
        return ServiceType.objects.get(code='payment-status')

    def test_free_text_creates_request_directly(self):
        conv, cl = self.route({'action': 'service', 'type': self.pay(), 'summary': 'استفسار عن صرف الفاتورة 55'})
        req = ServiceRequest.objects.get()
        self.assertEqual((req.service_type, req.source, req.subject), (self.pay(), 'whatsapp', 'استفسار عن صرف الفاتورة 55'))
        self.assertIn('الفاتورة رقم 55', req.details)
        self.assertEqual((conv.status, conv.bot_state), (S.CLOSED, ''))
        self.assertIn('صنّفنا طلبك تلقائيًا', self.sent[-1])
        self.assertIn(req.reference, self.sent[-1])
        cl.assert_called_once()

    def test_human_intent_hands_over(self):
        conv, _ = self.route({'action': 'human', 'type': None, 'summary': ''}, 'أريد التحدث مع موظف الآن')
        self.assertEqual((conv.bot_state, conv.status), ('human', S.NEW))
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_unclear_or_failure_falls_back_to_menu(self):
        for result in ({'action': 'unclear', 'type': None, 'summary': ''}, None):
            SupplierConversation.objects.all().delete()
            conv, _ = self.route(result, 'السلام عليكم ورحمة الله')
            self.assertEqual(conv.bot_state, 'menu')
            self.assertIn('اختر الخدمة', self.sent[-1])

    def test_short_text_and_digits_skip_the_model(self):
        with mock.patch('apps.whatsapp.ai.classify') as cl:
            self.say('مرحبا')              # أقصر من الحد: قائمة مباشرة
            self.say('1')                  # رقم خيار
        cl.assert_not_called()

    def test_free_text_while_in_menu_is_understood(self):
        self.say('مرحبا')
        conv, _ = self.route({'action': 'service', 'type': self.pay(), 'summary': 'ملخص'}, 'أحتاج كشف حساب الشهر الماضي')
        self.assertEqual(ServiceRequest.objects.count(), 1)
        self.assertEqual(conv.status, S.CLOSED)

    def test_unclear_in_menu_still_counts_attempts(self):
        self.say('مرحبا')
        conv, _ = self.route({'action': 'unclear', 'type': None, 'summary': ''}, 'كلام غير مفهوم أبدًا')
        self.assertEqual(conv.bot_attempts, 1)
        self.assertIn('لم أفهم', self.sent[-1])

    def test_collect_state_never_calls_the_model(self):
        self.say('مرحبا')
        self.say('1')
        with mock.patch('apps.whatsapp.ai.classify') as cl:
            self.say('هذه تفاصيل الطلب كاملة وطويلة')
        cl.assert_not_called()
        self.assertEqual(ServiceRequest.objects.count(), 1)
