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
