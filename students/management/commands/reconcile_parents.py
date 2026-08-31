"""Reconcile duplicate / orphan Parent records.

Groups parents by (normalised) email and merges runaways into a single
canonical row so password recovery and billing never hit dupes.

Default is a dry run that prints what WOULD change. Pass --commit to apply.

    python manage.py reconcile_parents            # dry run
    python manage.py reconcile_parents --commit   # apply
    python manage.py reconcile_parents --verbose  # show each child moved
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from students.models import Parent, Student, User


class Command(BaseCommand):
    help = "Merge duplicate Parent rows and report orphans (no linked user)."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true", help="Apply changes (default is a dry run).")
        parser.add_argument("--verbose", action="store_true", help="Show each child moved.")

    def handle(self, *args, **options):
        commit = options["commit"]
        verbose = options["verbose"]
        changed = 0

        grouped = defaultdict(list)
        for p in Parent.objects.all():
            email = (p.email or "").strip().lower()
            grouped[email or f"<no-email:{p.pk}>"].append(p)

        for key, rows in grouped.items():
            if len(rows) <= 1:
                continue
            owned = [p for p in rows if p.user_id]
            had_user = bool(owned)
            canonical = owned[0] if owned else sorted(rows, key=lambda p: p.created_at)[0]
            for dupe in [p for p in rows if p.pk != canonical.pk]:
                # Steal any genuinely useful display data before deleting.
                for field in ("parent_name", "phone_number", "address", "relationship_to_student"):
                    if not getattr(canonical, field) and getattr(dupe, field):
                        setattr(canonical, field, getattr(dupe, field))
                if dupe.user_id and not canonical.user_id:
                    canonical.user = dupe.user
                for child in Student.objects.filter(parent=dupe):
                    child.parent = canonical
                    if commit:
                        child.save()
                    changed += 1
                    if verbose:
                        self.stdout.write(f"  moved child #{child.pk} -> parent #{canonical.pk}")
                if commit:
                    canonical.save()
                    dupe.delete()
                self.stdout.write(
                    f"merged {1} dupe(s) for '{dupe.email or key}' "
                    f"{'into' if had_user else 'NO user previously, kept as'} parent #{canonical.pk}"
                )

        orphans = Parent.objects.filter(user__isnull=True)
        if orphans:
            self.stdout.write(f"\n{orphans.count()} parent(s) have no login user:")
        for p in orphans:
            if p.email:
                match = User.objects.filter(email__iexact=p.email.strip()).first()
                if match:
                    self.stdout.write(
                        f"  parent #{p.pk} '{p.parent_name}' -> link to user {match.email} "
                        f"({'COMMITTED' if commit else 'dry run'})"
                    )
                    if commit:
                        p.user = match
                        p.save()
                else:
                    self.stdout.write(
                        f"  parent #{p.pk} '{p.parent_name}' ({p.email or 'no email'}) "
                        f"has no matching user — centre must contact them."
                    )
            else:
                self.stdout.write(
                    f"  parent #{p.pk} '{p.parent_name}' has no email — cannot link."
                )

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {changed} child link(s) {'applied' if commit else 'to apply'}. "
            f"{'Applied changes.' if commit else 'Dry run only — re-run with --commit to apply.'}"
        ))
