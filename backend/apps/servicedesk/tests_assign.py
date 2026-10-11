"""
الإسناد لأي محاسب: لا ربط دائم بين المورد والمحاسب، والمشرف يوزّع كل طلب وقت وصوله.
"""
from django.urls import reverse

from apps.core.models import Notification

from . import services
from .models import ServiceRequest
from .services import RequestError
from django.contrib.auth import get_user_model

from .tests import Base, RT, S, make_user

User = get_user_model()


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
        for u in (self.acc1, self.agent):                    # كلاهما مطابق
            self.assertTrue(services.can_receive_assignment(u), u.username)
        for u in (self.sup, self.cfo, self.po, make_user('root', RT.ADMIN)):
            self.assertFalse(services.can_receive_assignment(u), u.username)
        root = User.objects.create_superuser('boss', password='x-Pass-12345')
        self.assertFalse(services.can_receive_assignment(root))
        self.acc2.is_active = False
        self.assertFalse(services.can_receive_assignment(self.acc2))

    def test_assignable_users_matches_can_receive(self):
        self.acc2.is_active = False
        self.acc2.save()
        got = set(services.assignable_users())
        self.assertEqual(got, {self.acc1, self.agent})
        for u in got:
            self.assertTrue(services.can_receive_assignment(u))

    def test_non_receivers_rejected(self):
        r = self.make()
        for u in (self.cfo, self.po, self.sup):
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
        note = Notification.objects.get()
        self.assertEqual(note.recipient, self.acc2)
        self.assertEqual(note.title, 'مهمة جديدة: يرجى المطابقة')
        self.assertIn(self.supplier.name, note.message)
        self.assertIn(r.reference, note.message)
        self.assertIn('يرجى مطابقة', note.message)


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
        self.assertEqual(set(Notification.objects.values_list('recipient__username', flat=True)), {'sup'})

    def test_non_supervisor_cannot_assign_on_create(self):
        with self.assertRaises(RequestError):
            self.make(user=self.agent, assign_to=self.acc1)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_non_receiver_rejected_and_nothing_created(self):
        with self.assertRaises(RequestError):
            self.make(user=self.sup, assign_to=self.cfo)
        self.assertEqual(ServiceRequest.objects.count(), 0)





