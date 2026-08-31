from datetime import date, timedelta

from django.core.management.base import BaseCommand

from students.models import (
    Invoice,
    Parent,
    ProgressReport,
    Session,
    Student,
)
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Seed a demo parent, child, and sample invoices/sessions/progress."

    def handle(self, *args, **options):
        email = "demo@example.com"
        password = "DemoPass123!"

        user, _ = User.objects.get_or_create(
            email=email,
            defaults={"email": email},
        )
        user.set_password(password)
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
            defaults={
                "year_group": "Year 8",
                "support_needed": "Maths and English support",
            },
        )

        Invoice.objects.filter(student=student).delete()
        Session.objects.filter(student=student).delete()
        ProgressReport.objects.filter(student=student).delete()

        today = date.today()
        Invoice.objects.create(
            student=student,
            description="April tuition",
            amount=120.00,
            due_date=today - timedelta(days=5),
            paid=True,
            paid_date=today - timedelta(days=3),
        )
        Invoice.objects.create(
            student=student,
            description="May tuition",
            amount=120.00,
            due_date=today + timedelta(days=10),
            paid=False,
        )

        Session.objects.create(
            student=student,
            subject="Maths",
            session_date=today - timedelta(days=7),
            duration=timedelta(hours=1),
            notes="Covered algebra: linear equations and factorising.",
        )
        Session.objects.create(
            student=student,
            subject="English",
            session_date=today - timedelta(days=4),
            duration=timedelta(hours=1),
            notes="Analysed descriptive writing for the 11+ exam.",
        )

        ProgressReport.objects.create(
            student=student,
            subject="Maths",
            grade="B",
            report_date=today - timedelta(days=2),
            comments="Good progress with equations; needs practice on word problems.",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded demo data: {user.email} / {password} (child: {student.student_name})"
            )
        )
