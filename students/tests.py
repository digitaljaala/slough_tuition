from datetime import date, timedelta
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import (
    LoginForm,
    ParentForm,
    StudentForm,
    UserRegistrationForm,
)
from .models import EnrolmentAgreement, Invoice, Parent, ProgressReport, Session, Student

User = get_user_model()


class StudentRegistrationTests(TestCase):
    def test_register_student_creates_parent_and_student(self):
        response = self.client.post(
            reverse("register_student"),
            {
                "parent_name": "Jane Smith",
                "relationship_to_student": "Mother",
                "phone_number": "01753 318318",
                "email": "Jane@Example.com",
                "address": "123 High Street",
                "student_name": "Sam Smith",
                "date_of_birth": "2012-05-10",
                "year_group": "Year 8",
                "subjects": "11_plus",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Parent.objects.count(), 1)
        self.assertEqual(Student.objects.count(), 1)

        parent = Parent.objects.get(parent_name="Jane Smith")
        student = Student.objects.get(student_name="Sam Smith")
        self.assertEqual(student.parent, parent)
        self.assertEqual(parent.email, "jane@example.com")


class ParentFormTests(TestCase):
    def test_rejects_invalid_uk_phone(self):
        form = ParentForm(
            {
                "parent_name": "Jane Smith",
                "phone_number": "123",
                "email": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("phone_number", form.errors)

    def test_accepts_mobile_and_strips_name(self):
        form = ParentForm(
            {
                "parent_name": "  Jane Smith  ",
                "relationship_to_student": "Mother",
                "phone_number": "07553 123565",
                "email": "  Jane@Example.com  ",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["parent_name"], "Jane Smith")
        self.assertEqual(form.cleaned_data["email"], "jane@example.com")


class StudentFormTests(TestCase):
    def test_rejects_future_date_of_birth(self):
        form = StudentForm(
            {
                "student_name": "Sam Smith",
                "year_group": "Year 8",
                "subjects": "11_plus",
                "date_of_birth": (date.today() + timedelta(days=1)).isoformat(),
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("date_of_birth", form.errors)

    def test_year_group_must_be_a_known_choice(self):
        form = StudentForm(
            {
                "student_name": "Sam Smith",
                "year_group": "Year Ninety",
                "subjects": "11_plus",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("year_group", form.errors)


class UserRegistrationFormTests(TestCase):
    def test_creates_user_with_email_and_lowercases(self):
        form = UserRegistrationForm(
            {
                "email": "Jane@Example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, "jane@example.com")
        self.assertTrue(user.check_password("StrongPass123!"))

    def test_rejects_duplicate_email(self):
        User.objects.create_user(email="jane@example.com", password="StrongPass123!")
        form = UserRegistrationForm(
            {
                "email": "JANE@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_rejects_mismatched_passwords(self):
        form = UserRegistrationForm(
            {
                "email": "jane@example.com",
                "password1": "StrongPass123!",
                "password2": "Different123!",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)


class AuthenticationFlowTests(TestCase):
    def test_register_login_logout_flow(self):
        self.client.post(
            reverse("register"),
            {
                "email": "parent@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertTrue(User.objects.filter(email="parent@example.com").exists())
        self.assertTrue("_auth_user_id" in self.client.session)

        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"username": "parent@example.com", "password": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue("_auth_user_id" in self.client.session)

        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_login_rejects_wrong_password(self):
        User.objects.create_user(
            email="parent@example.com", password="StrongPass123!"
        )
        response = self.client.post(
            reverse("login"),
            {"username": "parent@example.com", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse("_auth_user_id" in self.client.session)

    def test_login_form_rejects_unknown_email(self):
        form = LoginForm(data={"username": "nobody@example.com", "password": "x"})
        self.assertFalse(form.is_valid())

    def test_login_is_case_insensitive(self):
        User.objects.create_user(
            email="parent@example.com", password="StrongPass123!"
        )
        response = self.client.post(
            reverse("login"),
            {"username": "PARENT@EXAMPLE.COM", "password": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue("_auth_user_id" in self.client.session)

    def test_student_registration_links_parent_to_logged_in_user(self):
        user = User.objects.create_user(
            email="parent@example.com", password="StrongPass123!"
        )
        self.client.login(username="parent@example.com", password="StrongPass123!")
        self.client.post(
            reverse("register_student"),
            {
                "parent_name": "Jane Smith",
                "relationship_to_student": "Mother",
                "phone_number": "01753 318318",
                "email": "jane@example.com",
                "student_name": "Sam Smith",
                "date_of_birth": "2012-05-10",
                "year_group": "Year 8",
                "subjects": "11_plus",
            },
        )
        parent = Parent.objects.get(parent_name="Jane Smith")
        self.assertEqual(parent.user, user)


class MyAccountTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="parent@example.com", password="StrongPass123!"
        )
        self.parent = Parent.objects.create(
            user=self.user,
            parent_name="Jane Smith",
            phone_number="01753 318318",
            email="parent@example.com",
        )
        self.student = Student.objects.create(
            parent=self.parent,
            student_name="Sam Smith",
            year_group="Year 8",
        )

    def test_requires_login(self):
        response = self.client.get(reverse("my_account"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_shows_child_and_related_data(self):
        Invoice.objects.create(
            student=self.student,
            description="May tuition",
            amount=120.00,
            due_date=date.today(),
            paid=False,
        )
        Session.objects.create(
            student=self.student,
            subject="Maths",
            session_date=date.today(),
            duration=timedelta(hours=1),
        )
        ProgressReport.objects.create(
            student=self.student,
            subject="Maths",
            grade="B",
            report_date=date.today(),
        )
        self.client.login(username="parent@example.com", password="StrongPass123!")
        response = self.client.get(reverse("my_account"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sam Smith")
        self.assertContains(response, "May tuition")
        self.assertContains(response, "Maths")


class EnrolInviteFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="parent@example.com", password="StrongPass123!"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="OtherPass123!"
        )

    def _make_parent(self, *, token=True, user=None, email=None):
        return Parent.objects.create(
            user=user,
            parent_name="Jane Smith",
            phone_number="01753 318318",
            email=email or (user.email if user else "jane@example.com"),
            enrolment_token=uuid.uuid4() if token else None,
        )

    def test_enrol_without_token_redirects(self):
        self.client.login(username="parent@example.com", password="StrongPass123!")
        response = self.client.get(reverse("enrol"))
        self.assertRedirects(response, reverse("my_account"))

    def test_enrol_invalid_token_redirects(self):
        self.client.login(username="parent@example.com", password="StrongPass123!")
        response = self.client.get(reverse("enrol") + f"?token={uuid.uuid4()}")
        self.assertRedirects(response, reverse("my_account"))

    def test_enrol_unregistered_is_routed_to_register(self):
        parent = self._make_parent(user=None, email="invited@example.com")
        response = self.client.get(reverse("enrol") + f"?token={parent.enrolment_token}")
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("register"), response.url)
        self.assertIn("invited%40example.com", response.url)
        self.assertIn(reverse("enrol"), response.url)

    def test_enrol_token_for_another_user_is_denied(self):
        parent = self._make_parent(user=self.other_user)
        self.client.login(username="parent@example.com", password="StrongPass123!")
        response = self.client.get(reverse("enrol") + f"?token={parent.enrolment_token}")
        self.assertRedirects(response, reverse("my_account"))

    def test_enrol_valid_token_renders(self):
        parent = self._make_parent(user=self.user)
        self.client.login(username="parent@example.com", password="StrongPass123!")
        response = self.client.get(reverse("enrol") + f"?token={parent.enrolment_token}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane Smith")

    def test_submission_consumes_token_and_creates_enrolment(self):
        parent = self._make_parent(user=self.user)
        self.client.login(username="parent@example.com", password="StrongPass123!")
        payload = {
            "token": parent.enrolment_token,
            "student_name": "Sam Smith",
            "year_group": "Year 8",
            "subjects": "11_plus",
            "parent_name": "Jane Smith",
            "relationship_to_student": "Mother",
            "phone_number": "01753 318318",
            "email": "jane@example.com",
            "address": "1 High Street",
            "full_name": "John Smith",
            "relationship": "Father",
            "phone_number": "07553 123565",
            "details": "None",
            "additional_questions": "None",
            "pays_in_advance": "on",
            "pays_on_time": "on",
            "understands_no_refund": "on",
            "gives_24h_notice": "on",
            "child_on_time": "on",
            "confirm_terms": "on",
            "confirms_official_contact": "on",
        }
        response = self.client.post(reverse("enrol"), payload)
        self.assertRedirects(response, reverse("my_account"))
        parent.refresh_from_db()
        self.assertIsNone(parent.enrolment_token)
        student = Student.objects.get(student_name="Sam Smith")
        self.assertEqual(student.parent, parent)
        self.assertIsNotNone(EnrolmentAgreement.objects.filter(student=student).first())

    def test_unregistered_email_claim_links_user(self):
        parent = self._make_parent(user=None, email="invited@example.com")
        claimer = User.objects.create_user(
            email="invited@example.com", password="ClaimPass123!"
        )
        self.client.login(username="invited@example.com", password="ClaimPass123!")
        response = self.client.get(reverse("enrol") + f"?token={parent.enrolment_token}")
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        self.assertIsNotNone(parent.user)
        self.assertEqual(parent.user_id, claimer.pk)


from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from .models import Assessment, DeliveryType, PaymentPlan


class BillingFoundationTests(TestCase):
    def setUp(self):
        self.centre_plan = PaymentPlan.objects.create(
            name="Centre block",
            applies_to=DeliveryType.CENTRE,
            sessions_per_payment=8,
            base_price=Decimal("175.00"),
            assessment_fee=Decimal("25.00"),
        )
        user = User.objects.create_user(email="b@example.com", password="xPass123!")
        self.parent = Parent.objects.create(
            user=user,
            parent_name="Billing Parent",
            email="b@example.com",
            phone_number="01753 000000",
        )
        self.student = Student.objects.create(
            parent=self.parent,
            student_name="Billing Child",
            year_group="Year 8",
            delivery_type=DeliveryType.CENTRE,
            payment_plan=self.centre_plan,
        )

    def test_payment_plan_effective_price_uses_base_when_no_override(self):
        self.assertIsNone(self.centre_plan.custom_price)
        self.assertEqual(self.centre_plan.effective_price(), Decimal("175.00"))

    def test_payment_plan_custom_price_overrides_base(self):
        self.centre_plan.custom_price = Decimal("150.00")
        self.centre_plan.save()
        self.assertEqual(self.centre_plan.effective_price(), Decimal("150.00"))

    def test_assessment_model_records_marks(self):
        assessment = Assessment.objects.create(
            student=self.student,
            subject="Maths",
            assessment_date=date.today(),
            max_marks=50,
            marks=40,
            percentage=Decimal("80.0"),
        )
        self.assertEqual(assessment.percentage, Decimal("80.0"))
        self.assertEqual(assessment.student, self.student)

    def test_staff_group_lacks_billing_permissions(self):
        staff, _ = Group.objects.get_or_create(
            name="Staff (sessions & assessments)"
        )
        # Mirror the runtime seed_plans_and_roles command's grant set.
        for codename in [
            "add_student", "change_student",
            "add_session", "change_session", "delete_session",
            "add_assessment", "change_assessment", "delete_assessment",
        ]:
            perm = Permission.objects.filter(
                codename=codename,
                content_type__app_label="students",
            ).first()
            if perm:
                staff.permissions.add(perm)
        perms = set(staff.permissions.values_list("codename", flat=True))
        self.assertIn("add_session", perms)
        self.assertIn("add_assessment", perms)
        # Billing / pricing / admin-management must NOT be visible to staff.
        self.assertNotIn("change_invoice", perms)
        self.assertNotIn("change_paymentplan", perms)
        self.assertNotIn("add_user", perms)


from datetime import time as dtime
from django.contrib.auth.models import Group


class StaffConsoleTests(TestCase):
    def setUp(self):
        self.staff_group, _ = Group.objects.get_or_create(
            name="Staff (sessions & assessments)"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com", password="StaffPass123!"
        )
        self.staff.groups.add(self.staff_group)

        user = User.objects.create_user(email="p@example.com", password="xPass123!")
        self.parent = Parent.objects.create(
            user=user,
            parent_name="Console Parent",
            email="p@example.com",
            phone_number="01753 000000",
        )
        self.student = Student.objects.create(
            parent=self.parent,
            student_name="Console Child",
            year_group="Year 9",
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_staff_sees_dashboard(self):
        self.client.login(username="staff@example.com", password="StaffPass123!")
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/dashboard.html")

    def test_regular_user_cannot_access_console(self):
        self.client.login(username="p@example.com", password="xPass123!")
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_staff_can_create_session_via_console(self):
        self.client.login(username="staff@example.com", password="StaffPass123!")
        response = self.client.post(
            reverse("staff_session_create"),
            {
                "student": self.student.pk,
                "subject": "gcse_maths",
                "session_date": "2026-09-05",
                "start_time": "16:00",
                "duration": "01:00",
                "status": "scheduled",
                "notes": "Intro session",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Session.objects.count(), 1)
        session = Session.objects.get()
        self.assertEqual(session.status, "scheduled")
        self.assertEqual(session.start_time, dtime(16, 0))


class BookingBlockTests(TestCase):
    """Sub-modules 1 & 2: bookable list UI + centre 8-block consumption."""

    def setUp(self):
        self.staff_group, _ = Group.objects.get_or_create(
            name="Staff (sessions & assessments)"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com", password="StaffPass123!"
        )
        self.staff.groups.add(self.staff_group)

        user = User.objects.create_user(email="p@example.com", password="xPass123!")
        self.parent = Parent.objects.create(
            user=user,
            parent_name="Booking Parent",
            email="p@example.com",
            phone_number="01753 000000",
        )
        self.centre_plan = PaymentPlan.objects.create(
            name="Centre block",
            applies_to=DeliveryType.CENTRE,
            sessions_per_payment=8,
            base_price=Decimal("175.00"),
        )
        self.home_plan = PaymentPlan.objects.create(
            name="Home per session",
            applies_to=DeliveryType.HOME,
            sessions_per_payment=1,
            base_price=Decimal("30.00"),
        )
        self.centre_student = Student.objects.create(
            parent=self.parent,
            student_name="Centre Kid",
            year_group="Year 8",
            delivery_type=DeliveryType.CENTRE,
            payment_plan=self.centre_plan,
        )
        self.home_student = Student.objects.create(
            parent=self.parent,
            student_name="Home Kid",
            year_group="Year 9",
            delivery_type=DeliveryType.HOME,
            payment_plan=self.home_plan,
        )
        self.client.login(username="staff@example.com", password="StaffPass123!")

    def test_remaining_sessions_starts_full(self):
        self.assertEqual(self.centre_student.remaining_sessions, 8)

    def test_home_student_has_unlimited_remaining(self):
        self.assertIsNone(self.home_student.remaining_sessions)

    def test_booking_hub_renders_with_remaining_counts(self):
        response = self.client.get(reverse("staff_booking_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/booking_hub.html")
        self.assertContains(response, "Centre Kid")
        self.assertContains(response, "Home Kid")
        self.assertContains(response, "Unlimited")
        self.assertContains(response, "8 left")

    def test_session_create_consumes_one_centre_block_session(self):
        self.client.post(
            reverse("staff_session_create"),
            {
                "student": self.centre_student.pk,
                "subject": "gcse_maths",
                "session_date": "2026-09-10",
                "start_time": "16:00",
                "duration": "01:00",
                "status": "scheduled",
            },
        )
        self.centre_student.refresh_from_db()
        self.assertEqual(self.centre_student.sessions_used_in_block, 1)
        self.assertEqual(self.centre_student.remaining_sessions, 7)

    def test_session_create_does_not_consume_home_block(self):
        self.client.post(
            reverse("staff_session_create"),
            {
                "student": self.home_student.pk,
                "subject": "11_plus",
                "session_date": "2026-09-10",
                "start_time": "16:00",
                "duration": "01:00",
                "status": "scheduled",
            },
        )
        self.home_student.refresh_from_db()
        self.assertEqual(self.home_student.sessions_used_in_block, 0)

    def test_session_create_prefills_student_from_query_param(self):
        response = self.client.get(
            reverse("staff_session_create") + f"?student={self.centre_student.pk}"
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # The chosen student's option should be marked selected.
        self.assertIn(f'<option value="{self.centre_student.pk}" selected', html)
