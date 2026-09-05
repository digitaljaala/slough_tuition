from django.core.management.base import BaseCommand
from django.db import transaction

from students.models import Centre


class Command(BaseCommand):
    help = "Seed the franchise centres (Chalvey = head office, Manor Park = franchisee)."

    @transaction.atomic
    def handle(self, *args, **options):
        created = []
        for item in CENTRES:
            _, was_created = Centre.objects.get_or_create(
                slug=item["slug"],
                defaults={
                    "name": item["name"],
                    "is_head_office": item["head"],
                    "address": item["address"],
                    "session_slots": item["slots"],
                },
            )
            if was_created:
                created.append(item["name"])
        if created:
            msg = f"Created centres: {', '.join(created)}. "
            msg += "Existing centres left unchanged. Add future franchise locations as new Centre records."
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            self.stdout.write(
                self.style.SUCCESS("Centres already present — nothing to do.")
            )


CENTRES = [
    {
        "slug": "chalvey",
        "name": "Chalvey (Main Centre)",
        "head": True,
        "address": "Labour Memorial Hall, 52 High Street, Slough, SL1 2SQ",
        "slots": [
            {"days": ["Sat", "Sun"], "start": "10:00", "end": "12:00"},
            {"days": ["Sat", "Sun"], "start": "12:30", "end": "14:30"},
            {"days": ["Tue", "Thu"], "start": "17:00", "end": "19:00"},
        ],
    },
    {
        "slug": "manor-park",
        "name": "Manor Park",
        "head": False,
        "address": "Manor Park Community Centre, Villers Rd, Slough, SL2 1NP",
        "slots": [
            {"days": ["Sat", "Sun"], "start": "14:00", "end": "16:00"},
        ],
    },
]
