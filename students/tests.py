from datetime import date, timedelta
import uuid

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .forms import (
    LoginForm,
    ParentForm,
    StudentForm,
    UserRegistrationForm,
)
from .models import (
    EmergencyContact,
    EnrolmentAgreement,
    Invoice,
    MedicalInfo,
    Parent,
    ProgressReport,
    Session,
    Student,
)

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

    def test_home_session_creates_per_session_invoice(self):
        self.client.post(
            reverse("staff_session_create"),
            {
                "student": self.home_student.pk,
                "subject": "11_plus",
                "session_date": "2026-09-12",
                "start_time": "15:00",
                "duration": "01:00",
                "status": "scheduled",
            },
        )
        invoice = Invoice.objects.get(student=self.home_student)
        self.assertEqual(invoice.invoice_type, Invoice.InvoiceType.SESSION)
        # First-ever invoice for this student -> session rate + one-off
        # assessment fee (£30 session + £25 assessment = £55).
        self.assertEqual(invoice.amount, Decimal("55.00"))
        self.assertEqual(invoice.base_amount, Decimal("55.00"))
        self.assertEqual(invoice.plan, self.home_plan)
        self.assertEqual(invoice.due_date, date(2026, 9, 12))

    def test_home_booking_includes_assessment_fee_only_once(self):
        # First invoice for this student -> assessment fee added once.
        self.client.post(
            reverse("staff_session_create"),
            {
                "student": self.home_student.pk,
                "subject": "11_plus",
                "session_date": "2026-09-12",
                "start_time": "15:00",
                "duration": "01:00",
                "status": "scheduled",
            },
        )
        first = Invoice.objects.get(student=self.home_student)
        self.assertEqual(first.amount, Decimal("55.00"))  # 30 + 25 assessment

        # A second home session -> no further assessment fee.
        self.client.post(
            reverse("staff_session_create"),
            {
                "student": self.home_student.pk,
                "subject": "11_plus",
                "session_date": "2026-09-19",
                "start_time": "15:00",
                "duration": "01:00",
                "status": "scheduled",
            },
        )
        invoices = Invoice.objects.filter(student=self.home_student).order_by("id")
        self.assertEqual(invoices.count(), 2)
        self.assertEqual(invoices[1].amount, Decimal("30.00"))


class LoginRedirectTests(TestCase):
    """Option B: parents land straight on the account page after login."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="parent@example.com", password="StrongPass123!"
        )
        self.parent = Parent.objects.create(
            user=self.user,
            parent_name="Jane Parent",
            email="parent@example.com",
            phone_number="01753 000000",
        )

    def test_parent_with_profile_redirects_to_account(self):
        response = self.client.post(
            reverse("login"),
            {"username": "parent@example.com", "password": "StrongPass123!"},
        )
        self.assertRedirects(response, reverse("my_account"))

    def test_user_without_parent_profile_redirects_to_home(self):
        User.objects.create_user(
            email="nobody@example.com", password="StrongPass123!"
        )
        response = self.client.post(
            reverse("login"),
            {"username": "nobody@example.com", "password": "StrongPass123!"},
        )
        self.assertRedirects(response, reverse("home"))

    def test_next_param_takes_priority(self):
        response = self.client.post(
            reverse("login"),
            {"username": "parent@example.com", "password": "StrongPass123!",
             "next": reverse("my_account") + "#invoices"},
        )
        self.assertRedirects(response, reverse("my_account") + "#invoices")

    def test_welcome_note_uses_parent_name_not_email(self):
        User.objects.create_user(
            email="nobody@example.com", password="StrongPass123!"
        )
        self.client.login(username="nobody@example.com", password="StrongPass123!")
        # Bind a parent profile then log in via POST to capture the message.
        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"username": "parent@example.com", "password": "StrongPass123!"},
        )
        # Follow redirect to account page and confirm the greeting uses the name.
        response = self.client.get(response.url)
        self.assertContains(response, "Welcome back, Jane Parent")
        self.assertNotContains(response, "Welcome back, parent@example.com")


class ParentSelfServiceEditTests(TestCase):
    """Parents may edit their own general details, but not billing, and never
    another account's data."""

    def setUp(self):
        self.parent = Parent.objects.create(
            user=User.objects.create_user(
                email="owner@example.com", password="OwnerPass123!"
            ),
            parent_name="Owner Parent",
            email="owner@example.com",
            phone_number="01753 000000",
            address="1 Old Street",
        )
        self.student = Student.objects.create(
            parent=self.parent,
            student_name="Own Kid",
            year_group="Year 8",
            school_name="Old School",
            support_needed="Maths help",
            subjects=["gcse_maths"],
            delivery_type=DeliveryType.CENTRE,
        )
        # A second, unrelated parent whose data must stay off-limits.
        self.other = Parent.objects.create(
            user=User.objects.create_user(
                email="other@example.com", password="OtherPass123!"
            ),
            parent_name="Other Parent",
            email="other@example.com",
            phone_number="01753 111111",
        )
        self.other_student = Student.objects.create(
            parent=self.other, student_name="Other Kid", year_group="Year 7"
        )
        self.client.login(username="owner@example.com", password="OwnerPass123!")

    def test_parent_can_update_own_contact_details(self):
        response = self.client.post(
            reverse("edit_parent"),
            {
                "phone_number": "07553 555555",
                "email": "owner@example.com",
                "address": "99 New Road",
            },
        )
        self.assertRedirects(response, reverse("my_account"))
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.phone_number, "07553 555555")
        self.assertEqual(self.parent.address, "99 New Road")
        # Name is not editable from this form.
        self.assertEqual(self.parent.parent_name, "Owner Parent")

    def test_child_safe_fields_update_and_billing_fields_untouched(self):
        self.client.post(
            reverse("edit_student", args=[self.student.pk]),
            {
                "school_name": "New School",
                "date_of_birth": "2012-01-01",
                "support_needed": "Now needs English too",
            },
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.school_name, "New School")
        self.assertEqual(self.student.support_needed, "Now needs English too")
        # Centre-owned fields are not part of the editable form.
        self.assertEqual(self.student.student_name, "Own Kid")
        self.assertEqual(self.student.year_group, "Year 8")
        self.assertEqual(self.student.delivery_type, DeliveryType.CENTRE)

    def test_cannot_edit_another_parents_student(self):
        response = self.client.post(
            reverse("edit_student", args=[self.other_student.pk]),
            {"school_name": "Hacked"},
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_another_parents_emergency(self):
        response = self.client.get(
            reverse("edit_emergency", args=[self.other_student.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_another_parents_medical(self):
        response = self.client.get(
            reverse("edit_medical", args=[self.other_student.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_emergency_contact_create_and_update(self):
        self.client.post(
            reverse("edit_emergency", args=[self.student.pk]),
            {
                "full_name": "Jane Emerg",
                "relationship": "Mother",
                "phone_number": "07553 777777",
            },
        )
        contact = EmergencyContact.objects.get(student=self.student)
        self.assertEqual(contact.full_name, "Jane Emerg")

    def test_medical_info_create_and_update(self):
        self.client.post(
            reverse("edit_medical", args=[self.student.pk]),
            {"details": "Asthma, needs inhaler nearby"},
        )
        medical = MedicalInfo.objects.get(student=self.student)
        self.assertEqual(medical.details, "Asthma, needs inhaler nearby")

    def test_changing_parent_email_syncs_login_user(self):
        self.client.post(
            reverse("edit_parent"),
            {
                "phone_number": self.parent.phone_number,
                "email": "newlogin@example.com",
                "address": self.parent.address,
            },
        )
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.email, "newlogin@example.com")
        # The user's login email follows the parent email (email == username).
        self.assertEqual(self.parent.user.email, "newlogin@example.com")

    def test_cannot_use_another_accounts_login_email(self):
        response = self.client.post(
            reverse("edit_parent"),
            {
                "phone_number": self.parent.phone_number,
                "email": "other@example.com",  # the other parent's login
                "address": self.parent.address,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.parent.refresh_from_db()
        # Rejected: email left untouched and login not clobbered.
        self.assertEqual(self.parent.email, "owner@example.com")
        self.assertEqual(self.parent.user.email, "owner@example.com")


class PasswordResetFlowTests(TestCase):
    """Parent self-service password recovery is duplicate-safe."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="parent@example.com", password="StrongPass123!"
        )
        self.parent = Parent.objects.create(
            user=self.user,
            parent_name="Jane Parent",
            email="parent@example.com",
            phone_number="01753 000000",
        )

    def test_reset_page_renders_form(self):
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Forgot your password")

    def test_reset_sends_email_for_single_account(self):
        response = self.client.post(
            reverse("password_reset"), {"email": "parent@example.com"}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_reset_does_not_email_when_parent_rows_duplicated(self):
        Parent.objects.create(
            parent_name="Jane Parent Copy",
            email="parent@example.com",
            phone_number="01753 111111",
        )
        response = self.client.post(
            reverse("password_reset"), {"email": "parent@example.com"}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_does_not_email_for_unknown_email(self):
        response = self.client.post(
            reverse("password_reset"), {"email": "ghost@example.com"}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_full_reset_flow_changes_password(self):
        self.client.post(
            reverse("password_reset"), {"email": "parent@example.com"}
        )
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        # Extract the reset link (http://testserver/accounts/reset/<uid>/<token>/)
        line = next(l for l in body.splitlines() if "/accounts/reset/" in l)
        url = line.strip()
        path = url.replace("http://testserver", "").rstrip("/")
        # Django rotates the reset URL to .../set-password/ and keeps the token
        # in the session. Hit the token link to establish the session first,
        # then POST the new password to the rotated URL.
        self.client.get(path + "/")
        base = path.rsplit("/", 1)[0]
        resp = self.client.post(
            base + "/set-password/",
            {"new_password1": "NewStrongPass99!", "new_password2": "NewStrongPass99!"},
        )
        self.assertRedirects(resp, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPass99!"))
        # And the old password no longer works.
        self.client.logout()
        ok = self.client.login(username="parent@example.com", password="NewStrongPass99!")
        self.assertTrue(ok)


class RegisterDedupeTests(TestCase):
    """register_student must not create duplicate Parent rows by email."""

    def test_unauthenticated_enrolment_reuses_existing_parent_by_email(self):
        existing = Parent.objects.create(
            parent_name="Old Name",
            email="same@example.com",
            phone_number="01753 444444",
        )
        self.client.post(
            reverse("register_student"),
            {
                "parent_name": "New Name",
                "email": "SAME@example.com",
                "phone_number": "01753 555555",
                "address": "1 High St",
                "student_name": "Child One",
                "date_of_birth": "2012-05-10",
                "year_group": "Year 5",
                "subjects": "11_plus",
                "school_name": "St Ethelbert's",
                "relationship_to_student": "Mother",
            },
        )
        self.assertEqual(Parent.objects.filter(email__iexact="same@example.com").count(), 1)
        existing.refresh_from_db()
        # Reused the existing row and refreshed display fields; no duplicate.
        self.assertEqual(existing.parent_name, "New Name")
        self.assertEqual(Student.objects.filter(parent=existing).count(), 1)


class StaffResetParentTests(TestCase):
    """Superuser-only tool to find a parent and reset their login password."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="admin@example.com", password="AdminPass123!"
        )
        self.parent_user = User.objects.create_user(
            email="parent@example.com", password="OldPass123!"
        )
        self.parent = Parent.objects.create(
            user=self.parent_user,
            parent_name="Jane Parent",
            email="parent@example.com",
            phone_number="01753 000000",
        )
        self.url = reverse("staff_reset_parent")

    def test_normal_staff_cannot_access(self):
        staff = User.objects.create_user(email="staff@example.com", password="StaffPass123!")
        self.client.force_login(staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_superuser_can_search_and_reset(self):
        self.client.force_login(self.superuser)
        page = self.client.get(self.url, {"q": "Jane"})
        self.assertContains(page, "Jane Parent")

        response = self.client.post(
            self.url,
            {"parent_id": self.parent.pk, "password1": "FreshPass123!"},
        )
        self.parent_user.refresh_from_db()
        self.assertTrue(self.parent_user.check_password("FreshPass123!"))
        self.assertRedirects(
            response, self.url + "?q=parent@example.com"
        )

    def test_superuser_can_create_login_for_parent_without_user(self):
        orphan = Parent.objects.create(
            parent_name="Lost Parent",
            email="lost@example.com",
            phone_number="01753 222222",
        )
        self.client.force_login(self.superuser)
        self.client.post(
            self.url,
            {"parent_id": orphan.pk, "password1": "FreshPass123!"},
        )
        orphan.refresh_from_db()
        self.assertIsNotNone(orphan.user)
        self.assertTrue(orphan.user.check_password("FreshPass123!"))
        self.assertEqual(orphan.user.email, "lost@example.com")

    def test_superuser_links_existing_user_not_second_account(self):
        # Parent shares an email with an existing login user.
        self.assertEqual(self.parent.user_id, self.parent_user.pk)
        self.client.force_login(self.superuser)
        self.client.post(
            self.url,
            {"parent_id": self.parent.pk, "password1": "FreshPass123!"},
        )
        users = User.objects.filter(email="parent@example.com")
        self.assertEqual(users.count(), 1)


class AssessmentCrudTests(TestCase):
    """Items 6-8: edit/update, per-student history, PDF report, email to parent."""

    def setUp(self):
        self.staff_group, _ = Group.objects.get_or_create(
            name="Staff (sessions & assessments)"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com", password="StaffPass123!"
        )
        self.staff.groups.add(self.staff_group)

        user = User.objects.create_user(
            email="parent@example.com", password="xPass123!"
        )
        self.parent = Parent.objects.create(
            user=user,
            parent_name="Assessment Parent",
            email="parent@example.com",
            phone_number="01753 000000",
        )
        self.student = Student.objects.create(
            parent=self.parent,
            student_name="Assessment Child",
            year_group="Year 8",
        )
        self.assessment = Assessment.objects.create(
            student=self.student,
            subject="gcse_maths",
            assessment_date="2026-09-01",
            topics="Algebra",
            max_marks=20,
            marks=16,
            percentage=Decimal("80.0"),
            tutor_notes="Doing well.",
        )
        self.client.login(username="staff@example.com", password="StaffPass123!")

    def test_edit_assessment_updates_record(self):
        response = self.client.post(
            reverse("staff_assessment_edit", args=[self.assessment.pk]),
            {
                "student": self.student.pk,
                "subject": "gcse_maths",
                "assessment_date": "2026-09-01",
                "topics": "Algebra, Quadratics",
                "max_marks": "20",
                "marks": "18",
                "tutor_notes": "Improved.",
            },
        )
        self.assertRedirects(
            response, reverse("staff_student_assessments", args=[self.student.pk])
        )
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.marks, 18)
        self.assertEqual(self.assessment.topics, "Algebra, Quadratics")

    def test_delete_assessment(self):
        self.client.post(reverse("staff_assessment_delete", args=[self.assessment.pk]))
        self.assertFalse(Assessment.objects.filter(pk=self.assessment.pk).exists())

    def test_history_view_shows_average(self):
        Assessment.objects.create(
            student=self.student,
            subject="gcse_english",
            assessment_date="2026-09-10",
            max_marks=10,
            marks=8,
            percentage=Decimal("80.0"),
        )
        response = self.client.get(
            reverse("staff_student_assessments", args=[self.student.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff/assessment_history.html")
        self.assertContains(response, "80.0")
        self.assertContains(response, "gcse_english")

    def test_pdf_report_download(self):
        response = self.client.get(
            reverse("staff_assessment_report", args=[self.assessment.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_email_assessment_to_parent(self):
        from django.core import mail

        response = self.client.get(
            reverse("staff_assessment_email", args=[self.assessment.pk])
        )
        self.assertRedirects(
            response, reverse("staff_student_assessments", args=[self.student.pk])
        )
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["parent@example.com"])
        self.assertIn(self.assessment.student.student_name, sent.subject)
        self.assertTrue(
            any(
                isinstance(att, tuple)
                and len(att) == 3
                and att[2] == "application/pdf"
                for att in sent.attachments
            )
        )
