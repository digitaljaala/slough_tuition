from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from students.models import DeliveryType, PaymentPlan


# Permissions that a normal staff user should have. Billing, pricing, parent
# fee fields and user/staff management are intentionally EXCLUDED so a staff
# member can book sessions and enter assessments but never touch money or
# access control.
STAFF_MODEL_PERMISSIONS = {
    "student": {"view", "add", "change"},
    "session": {"view", "add", "change", "delete"},
    "assessment": {"view", "add", "change", "delete"},
    "progressreport": {"view", "add", "change"},
    "progresslog": {"view", "add", "change"},
}


class Command(BaseCommand):
    help = "Seed default payment plans and staff/superuser role groups."

    @transaction.atomic
    def handle(self, *args, **options):
        self._seed_plans()
        self._seed_groups()

    def _seed_plans(self):
        centre, _ = PaymentPlan.objects.get_or_create(
            name="Centre 8-session block",
            defaults={
                "applies_to": DeliveryType.CENTRE,
                "sessions_per_payment": 8,
                "base_price": Decimal("175.00"),
                "assessment_fee": Decimal("25.00"),
            },
        )
        home, _ = PaymentPlan.objects.get_or_create(
            name="Home tuition (per session)",
            defaults={
                "applies_to": DeliveryType.HOME,
                "sessions_per_payment": 1,
                "base_price": Decimal("30.00"),
                "assessment_fee": Decimal("25.00"),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Payment plans ready: '{centre.name}' and '{home.name}'. "
                "Adjust home per-session rate / add custom deals in admin."
            )
        )

    def _seed_groups(self):
        # Superuser role: Django superusers automatically bypass model
        # permissions, so staff_group is the only group we need to create.
        staff, created = Group.objects.get_or_create(name="Staff (sessions & assessments)")
        if created:
            self.stdout.write(self.style.SUCCESS("Created 'Staff' group."))

        perms = []
        # Scope strictly to the 'students' app, so we never accidentally grant
        # a same-named permission from another app.
        for model_name, actions in STAFF_MODEL_PERMISSIONS.items():
            for action in actions:
                codename = f"{action}_{model_name}"
                for perm in Permission.objects.filter(
                    codename=codename,
                    content_type__app_label="students",
                ):
                    perms.append(perm)

        staff.permissions.set(perms)
        self.stdout.write(
            self.style.SUCCESS(
                f"'Staff' group now holds {len(perms)} permissions "
                "(sessions, assessments, basic student/progress views)."
            )
        )
