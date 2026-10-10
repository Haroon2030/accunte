"""
الإسناد لأي محاسب: لا ربط دائم بين المورد والمحاسب، والمشرف يوزّع كل طلب وقت وصوله.
"""
from django.urls import reverse

from apps.core.models import Notification

from . import services
from .models import ServiceRequest
from .services import RequestError
from .tests import Base, RT, S, make_user


class AssignAnyoneTests(Base):
    def test_meeting_request_can_go_to_an_accountant_and_he_can_work_it(self):
        r = self.make(self.t_meet, fields={'f_preferred_date': '2026-03-01', 'f_topic': 'مراجعة'})                                    # نوع لا يعالجه المحاسبون أصلًا
        services.assign(r.pk, self.acc1, self.sup)
        r.refresh_from_db()
        self.assertEqual(r.assigned_to, self.acc1)
        services.transition(r.pk, S.IN_PROGRESS, self.acc1)           # المسنَد إليه يبدأ طلبه
        r.refresh_from_db()
        self.assertEqual(r.status, S.IN_PROGRESS)

    def test_unassigned_accountant_still_cannot_touch_that_type(self):
        r = self.make(self.t_meet, fields={'f_preferred_date': '2026-03-01', 'f_topic': 'مراجعة'})
        with self.assertRaises(RequestError):
            services.transition(r.pk, S.IN_PROGRESS, self.acc1)

    def test_who_can_receive(self):
        for u in (self.acc1, self.agent, self.sup):
            self.assertTrue(services.can_receive_assignment(u), u.username)
        for u in (self.cfo, self.aud, self.po):
            self.assertFalse(services.can_receive_assignment(u), u.username)
        self.acc2.is_active = False
        self.assertFalse(services.can_receive_assignment(self.acc2))

    def test_assignable_users_matches_can_receive(self):
        self.acc2.is_active = False
        self.acc2.save()
        root = make_user('root', RT.ADMIN)
        got = set(services.assignable_users())
        self.assertEqual(got, {self.sup, self.agent, self.acc1, root})
        for u in got:
            self.assertTrue(services.can_receive_assignment(u))

    def test_non_receivers_rejected(self):
        r = self.make()
        for u in (self.cfo, self.aud, self.po):
            with self.assertRaises(RequestError):
                services.assign(r.pk, u, self.sup)

    def test_only_supervisors_assign(self):
        r = self.make()
        with self.assertRaises(RequestError):
            services.assign(r.pk, self.acc1, self.agent)

    def test_assign_notifies_only_assignee_and_audits(self):
        r = self.make()
        Notification.objects.all().delete()
        services.assign(r.pk, self.acc2, self.sup)
        self.assertEqual(list(Notification.objects.values_list('recipient__username', flat=True)), ['acc2'])


class CreateWithAssigneeTests(Base):
    def test_supervisor_assigns_on_create_and_only_assignee_is_notified(self):
        Notification.objects.all().delete()
        r = self.make(user=self.sup, assign_to=self.acc2)
        self.assertEqual(r.assigned_to, self.acc2)
        self.assertEqual(set(Notification.objects.values_list('recipient__username', flat=True)), {'acc2'})

    def test_without_assignee_destination_role_is_notified(self):
        Notification.objects.all().delete()
        r = self.make(user=self.sup)
        self.assertIsNone(r.assigned_to)
        self.assertEqual(set(Notification.objects.values_list('recipient__username', flat=True)), {'acc1', 'acc2'})

    def test_non_supervisor_cannot_assign_on_create(self):
        with self.assertRaises(RequestError):
            self.make(user=self.agent, assign_to=self.acc1)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_non_receiver_rejected_and_nothing_created(self):
        with self.assertRaises(RequestError):
            self.make(user=self.sup, assign_to=self.cfo)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_create_view_assign_to(self):
        self.client.force_login(self.sup)
        data = {'step': 'create', 'type': self.t_pay.pk, 'supplier': self.supplier.pk, 'subject': 'س', 'f_invoice_number': 'I1',
                'assign_to': self.acc2.pk}
        self.client.post(reverse('servicedesk:create'), data)
        self.assertEqual(ServiceRequest.objects.get().assigned_to, self.acc2)

    def test_create_view_rejects_unlisted_user(self):
        self.client.force_login(self.sup)
        data = {'step': 'create', 'type': self.t_pay.pk, 'supplier': self.supplier.pk, 'subject': 'س', 'f_invoice_number': 'I1',
                'assign_to': self.cfo.pk}
        self.client.post(reverse('servicedesk:create'), data)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_agent_form_has_no_assign_field(self):
        self.client.force_login(self.agent)
        self.assertNotContains(self.client.get(reverse('servicedesk:create'), {'type': self.t_pay.pk}), 'name="assign_to"')
        self.client.force_login(self.sup)
        self.assertContains(self.client.get(reverse('servicedesk:create'), {'type': self.t_pay.pk}), 'name="assign_to"')


class ListInlineAssignTests(Base):
    def test_inline_form_only_for_supervisor_on_unassigned_open_requests(self):
        r = self.make()
        url = reverse('servicedesk:list')
        self.client.force_login(self.sup)
        self.assertContains(self.client.get(url), reverse('servicedesk:assign', args=[r.pk]))
        self.client.force_login(self.agent)
        self.assertNotContains(self.client.get(url), reverse('servicedesk:assign', args=[r.pk]))

    def test_no_inline_form_once_assigned(self):
        r = self.make()
        services.assign(r.pk, self.acc1, self.sup)
        self.client.force_login(self.sup)
        self.assertNotContains(self.client.get(reverse('servicedesk:list')), reverse('servicedesk:assign', args=[r.pk]))

    def test_next_redirect_back_to_list(self):
        r = self.make()
        self.client.force_login(self.sup)
        resp = self.client.post(reverse('servicedesk:assign', args=[r.pk]),
                                {'agent': self.acc1.pk, 'next': '/service-requests/?status=new'})
        self.assertRedirects(resp, '/service-requests/?status=new', fetch_redirect_response=False)
        r.refresh_from_db()
        self.assertEqual(r.assigned_to, self.acc1)

    def test_unsafe_next_is_ignored(self):
        for bad in ('//evil.test/', 'https://evil.test/', '/other/'):
            r = self.make()
            self.client.force_login(self.sup)
            resp = self.client.post(reverse('servicedesk:assign', args=[r.pk]), {'agent': self.acc1.pk, 'next': bad})
            self.assertNotIn('evil', resp['Location'], bad)
            self.assertNotEqual(resp['Location'], '/other/', bad)
