from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from students.models import Assessment, AssessmentSubject, Parent, Student

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Seed dummy assessment data (up to 5 subjects each) so the "
        "multi-subject assessment form, list and history views can be checked."
    )

    def handle(self, *args, **options):
        email = "demo@example.com"
        user, _ = User.objects.get_or_create(
            email=email, defaults={"email": email}
        )
        user.set_password("DemoPass123!")
        user.save()

        parent, _ = Parent.objects.get_or_create(
            user=user,
            defaults={
                "parent_name": "Demo Parent",
                "email": email,
                "phone_number": "01753 000000",
            },
        )

        student, _ = Student.objects.get_or_create(
            parent=parent,
            student_name="Demo Child",
            defaults={"year_group": "Year 8"},
        )

        # A single-subject assessment.
        self._make_assessment(
            student,
            date.today() - timedelta(days=21),
            [
                ("Mathematics", "Year 8", 20, 16),
            ],
        )
        # A three-subject assessment.
        self._make_assessment(
            student,
            date.today() - timedelta(days=10),
            [
                ("Mathematics", "Year 8", 40, 32),
                ("English", "Year 8", 50, 38),
                ("Science", "Year 8", 30, 21),
            ],
        )
        # A five-subject assessment (the maximum).
        self._make_assessment(
            student,
            date.today() - timedelta(days=2),
            [
                ("Mathematics", "Year 9", 25, 20),
                ("English", "Year 9", 25, 15),
                ("English Literature", "Year 9", 25, 19),
                ("Science", "Year 9", 25, 22),
                ("Verbal Reasoning", "Year 9", 30, 24),
            ],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded dummy assessments for {student.student_name} "
                f"(parent login {email} / DemoPass123!)."
            )
        )

    def _make_assessment(self, student, assessment_date, subjects):
        assessment = Assessment.objects.create(
            student=student,
            assessment_date=assessment_date,
            tutor_notes="Dummy data seeded for testing the multi-subject form.",
        )
        for subject, year_group, max_marks, marks in subjects:
            AssessmentSubject.objects.create(
                assessment=assessment,
                subject=subject,
                year_group=year_group,
                max_marks=max_marks,
                marks=marks,
                percentage=Decimal(marks) / Decimal(max_marks) * 100,
            )
        assessment.recompute_overall()
        assessment.save(update_fields=["overall_percentage"])
