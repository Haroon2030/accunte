"""
التحديث اللحظي للصندوق: نقاط JSON المتزايدة، قراءة الرسائل عند الاستعلام، والإرسال بلا إعادة تحميل.
"""
import datetime
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from . import services
from .client import WhatsAppError
from .models import ConversationMessage as M
from .tests_inbox import NUMBER, S, Base


class LiveBase(Base):
    def setUp(self):
        super().setUp()
        self.c = self.conv(status=S.OPEN, assigned_agent=self.a1, unread_count=0)

    def msg(self, wa_id, direction='in', body='نص', **kw):
        return M.objects.create(conversation=self.c, direction=direction, wa_message_id=wa_id, body=body, **kw)

    def live(self, user, **params):
        self.client.force_login(user)
        return self.client.get(reverse('whatsapp_inbox:conversation_live', args=[self.c.pk]), params)


class ConversationLiveTests(LiveBase):
    def test_returns_only_messages_after_cursor(self):
        m1, m2, m3 = self.msg('A'), self.msg('B'), self.msg('C')
        data = self.live(self.a1, after=m1.pk).json()
        self.assertEqual([m['id'] for m in data['messages']], [m2.pk, m3.pk])
        self.assertIn('نص', data['messages'][0]['html'])
        self.assertEqual(self.live(self.a1, after=m3.pk).json()['messages'], [])

    def test_never_cached(self):
        self.assertEqual(self.live(self.a1)['Cache-Control'], 'no-store')

    def test_login_and_role_required(self):
        url = reverse('whatsapp_inbox:conversation_live', args=[self.c.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.acc)                  # المحاسب لا يملك صلاحية الصندوق
        self.assertIn(self.client.get(url).status_code, (302, 403))

    def test_incoming_marks_read_only_for_who_can_act(self):
        self.c.unread_count = 2
        self.c.save()
        self.msg('A')
        self.live(self.cfo)                                # المدير المالي سوبر أدمن: يتصرف فيقرأها
        self.c.refresh_from_db()
        self.assertEqual(self.c.unread_count, 0)
        self.c.unread_count = 2
        self.c.save()
        self.live(self.a1)
        self.c.refresh_from_db()
        self.assertEqual(self.c.unread_count, 0)

    def test_outbound_only_poll_does_not_mark_read(self):
        self.c.unread_count = 1
        self.c.save()
        self.msg('O', direction='out', status='sent', sent_by=self.a1)
        self.live(self.a1)
        self.c.refresh_from_db()
        self.assertEqual(self.c.unread_count, 1)

    def test_status_change_of_known_outbound_is_pushed_once(self):
        out = self.msg('O', direction='out', status='pending', sent_by=self.a1)
        same = self.live(self.a1, after=out.pk, known=f'{out.pk}:pending').json()
        self.assertEqual(same['updates'], [])
        out.status = 'delivered'
        out.save()
        changed = self.live(self.a1, after=out.pk, known=f'{out.pk}:pending').json()
        self.assertEqual([u['id'] for u in changed['updates']], [out.pk])
        self.assertEqual(self.live(self.a1, after=out.pk, known=f'{out.pk}:delivered').json()['updates'], [])

    def test_known_ignores_garbage_and_inbound(self):
        inbound = self.msg('I')
        data = self.live(self.a1, after=inbound.pk, known=f'x:y,,{inbound.pk}:new,:,99999:sent').json()
        self.assertEqual(data['updates'], [])

    def test_known_is_capped(self):
        self.assertEqual(len(services_parse(','.join(f'{i}:sent' for i in range(500)))), 60)

    def test_meta_reports_status_version_and_late(self):
        data = self.live(self.a1).json()
        self.assertEqual((data['status'], data['version'], data['late_minutes']), ('open', self.c.version, 0))
        self.c.awaiting_reply_since = timezone.now() - datetime.timedelta(hours=3)
        self.c.save()
        self.assertGreaterEqual(self.live(self.a1).json()['late_minutes'], 150)

    def test_version_changes_after_assignment_by_someone_else(self):
        before = self.live(self.a1).json()['version']
        services.assign(self.c.pk, self.a2, self.sup)
        self.assertGreater(self.live(self.sup).json()['version'], before)


def services_parse(raw):
    from .inbox_views import _parse_known
    return _parse_known(raw)


class SendAjaxTests(LiveBase):
    def post(self, user, text='مرحبا'):
        self.client.force_login(user)
        return self.client.post(reverse('whatsapp_inbox:send_ajax', args=[self.c.pk]), {'text': text})

    def test_success_returns_message_html_and_sends(self):
        with mock.patch('apps.whatsapp.client.send_text', return_value={'key': {'id': 'OUT-9'}}):
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.post(self.a1, 'تم التحويل')
        data = resp.json()
        self.assertTrue(data['ok'])
        msg = M.objects.get(pk=data['id'])
        self.assertEqual((msg.body, msg.status, msg.wa_message_id), ('تم التحويل', 'sent', 'OUT-9'))
        self.assertIn(f'data-msg-id="{msg.pk}"', data['html'])
        self.assertEqual(resp['Cache-Control'], 'no-store')

    def test_gateway_failure_still_returns_message_marked_failed(self):
        with mock.patch('apps.whatsapp.client.send_text', side_effect=WhatsAppError('تعذر الاتصال')):
            with self.captureOnCommitCallbacks(execute=True):
                data = self.post(self.a1).json()
        self.assertTrue(data['ok'])
        self.assertEqual(M.objects.get(pk=data['id']).status, 'failed')

    def test_empty_text_is_400_with_error(self):
        resp = self.post(self.a1, '   ')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['ok'])
        self.assertTrue(resp.json()['error'])
        self.assertEqual(M.objects.count(), 0)

    def test_viewer_cannot_send(self):
        with mock.patch('apps.whatsapp.client.send_text') as sent:
            resp = self.post(self.acc)
        self.assertIn(resp.status_code, (302, 400, 403))   # المحاسب بلا صلاحية الصندوق: يُردّ قبل الإرسال
        sent.assert_not_called()
        self.assertEqual(M.objects.count(), 0)

    def test_get_not_allowed_and_anonymous_redirected(self):
        url = reverse('whatsapp_inbox:send_ajax', args=[self.c.pk])
        self.assertEqual(self.client.post(url, {'text': 'x'}).status_code, 302)
        self.client.force_login(self.a1)
        self.assertEqual(self.client.get(url).status_code, 405)


class InboxLiveTests(Base):
    url = staticmethod(lambda: reverse('whatsapp_inbox:live'))

    def test_unchanged_signature_returns_no_html(self):
        self.conv(status=S.NEW, unread_count=1)
        self.client.force_login(self.sup)
        first = self.client.get(self.url()).json()
        self.assertTrue(first['changed'])
        self.assertIn(NUMBER[-4:], first['html'])
        again = self.client.get(self.url(), {'sig': first['sig']}).json()
        self.assertEqual(again, {'changed': False, 'sig': first['sig']})

    def test_new_conversation_or_counter_changes_signature(self):
        c = self.conv(status=S.NEW, unread_count=1)
        self.client.force_login(self.sup)
        sig = self.client.get(self.url()).json()['sig']
        c.unread_count = 2
        c.save()
        self.assertTrue(self.client.get(self.url(), {'sig': sig}).json()['changed'])
        sig = self.client.get(self.url()).json()['sig']
        self.conv(status=S.NEW, number='966509999999', unread_count=1)
        self.assertTrue(self.client.get(self.url(), {'sig': sig}).json()['changed'])

    def test_no_store_and_requires_inbox_role(self):
        self.client.force_login(self.sup)
        self.assertEqual(self.client.get(self.url())['Cache-Control'], 'no-store')
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code, 302)
        self.client.force_login(self.acc)
        self.assertIn(self.client.get(self.url()).status_code, (302, 403))

    def test_inbox_page_embeds_signature_and_live_url(self):
        self.client.force_login(self.sup)
        html = self.client.get(reverse('whatsapp_inbox:inbox')).content.decode()
        self.assertIn('data-live-url="/inbox/live/"', html)
        self.assertRegex(html, r'data-sig="[0-9a-f]{16}"')
