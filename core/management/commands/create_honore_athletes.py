from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import Athlete


ATHLETE_NAMES = [
    "Madison Welby",
    "Alana Dijkman",
    "Alexander Stefas",
    "Julia Seppenwoolde",
    "Tijmen van Veen",
    "Jesse Leenvaar",
    "Aarna Thakare",
    "Mohammed Mobelfqih",
    "Jort Minnaard",
    "Lasse Wiegemans",
    "Celine van Heerikhuize",
    "Inaya Yahyaoui",
    "Quirijn Pastoor",
    "Daan van Dessel",
    "Max Swabedisen",
    "Lars Vreugdenhil",
    "Nora Ebbing",
    "Sarah Peerik",
    "Jarvin Sterkenburg",
    "Manolo Pierson",
    "Gijs de Haan",
    "Tess Goessens",
    "Thelma Solleveld",
]


ZONE_SPEEDS_MPS = {
    "1": 1000 / (7 * 60),
    "2": 1000 / (6 * 60),
    "3": 1000 / (5 * 60),
    "4": 1000 / (4 * 60),
    "5": 1000 / (3 * 60),
}


class Command(BaseCommand):
    help = "Create Honore Hoedt athlete profiles with fictional manual zones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner",
            default="Honore Hoedt",
            help="Coach account username or full name. Defaults to 'Honore Hoedt'.",
        )

    def handle(self, *args, **options):
        owner = self._find_owner(options["owner"])
        created = []
        updated = []
        conflicts = []

        for name in ATHLETE_NAMES:
            existing = Athlete.objects.filter(name__iexact=name).first()
            if existing:
                if existing.owner_id != owner.id:
                    conflicts.append(f"{name} (already owned by {existing.owner})")
                    continue
                existing.birth_year = 1900
                existing.gender = "X"
                existing.zone_method = "manual"
                existing.zone_speed_mps = dict(ZONE_SPEEDS_MPS)
                existing.save(update_fields=["birth_year", "gender", "zone_method", "zone_speed_mps"])
                updated.append(name)
                continue

            Athlete.objects.create(
                owner=owner,
                name=name,
                birth_year=1900,
                gender="X",
                zone_method="manual",
                zone_speed_mps=dict(ZONE_SPEEDS_MPS),
            )
            created.append(name)

        self.stdout.write(self.style.SUCCESS(
            f"Owner: {owner.username} | created {len(created)} | updated {len(updated)} | conflicts {len(conflicts)}"
        ))
        if created:
            self.stdout.write("Created: " + ", ".join(created))
        if updated:
            self.stdout.write("Updated: " + ", ".join(updated))
        if conflicts:
            self.stdout.write(self.style.WARNING("Conflicts: " + "; ".join(conflicts)))

    def _find_owner(self, value):
        User = get_user_model()
        raw = (value or "").strip()
        candidates = [
            raw,
            raw.replace(" ", "_"),
            raw.replace(" ", "."),
            raw.replace(" ", ""),
        ]
        for candidate in candidates:
            user = User.objects.filter(username__iexact=candidate).first()
            if user:
                return user

        parts = raw.split()
        if len(parts) >= 2:
            user = User.objects.filter(first_name__iexact=parts[0], last_name__iexact=" ".join(parts[1:])).first()
            if user:
                return user

        raise CommandError(f"Owner account not found for '{raw}'.")
