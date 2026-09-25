from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import Athlete


ACCOUNT_ROWS = [
    ("Madison Welby", "MW3000m!!"),
    ("Alana Dijkman", "AD800m!!!"),
    ("Alexander Stefas", "AS800m!!!"),
    ("Julia Seppenwoolde", "JS400m!!!"),
    ("Tijmen van Veen", "TVV1500m!!"),
    ("Jesse Leenvaar", "JL800m!!"),
    ("Aarna Thakare", "AK800m!!!"),
    ("Mohammed Mobelfqih", "MM1500m!!"),
    ("Jort Minnaard", "JM800m!!!"),
    ("Lasse Wiegemans", "LW800m!!!"),
    ("Celine van Heerikhuize", "CVH1500m!!"),
    ("Inaya Yahyaoui", "IY5000m!!"),
    ("Quirijn Pastoor", "QP1609m!!"),
    ("Daan van Dessel", "DVD1500m!!"),
    ("Max Swabedisen", "MS1500m@@@"),
    ("Lars Vreugdenhil", "LV1500m##!"),
    ("Nora Ebbing", "NE800m!!!"),
    ("Sarah Peerik", "SPCross15!!"),
    ("Jarvin Sterkenburg", "JS1500m!!!"),
    ("Manolo Pierson", "MP5ksub8!"),
    ("Wilbert van Vliet", "WVV1500m!!"),
    ("Gijs de Haan", "GDH1500m!!"),
    ("Tess Goessens", "TG800m800m!!"),
    ("Thelma Solleveld", "TS800m!##"),
]


class Command(BaseCommand):
    help = "Create athlete login accounts for Honore Hoedt athletes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner",
            default="Honore Hoedt",
            help="Coach account username or full name. Defaults to 'Honore Hoedt'.",
        )

    def handle(self, *args, **options):
        owner = self._find_owner(options["owner"])
        User = get_user_model()
        created = []
        updated = []
        missing_athletes = []
        conflicts = []

        for athlete_name, password in ACCOUNT_ROWS:
            athlete = Athlete.objects.filter(name__iexact=athlete_name).first()
            if not athlete:
                missing_athletes.append(athlete_name)
                continue
            if athlete.owner_id != owner.id:
                conflicts.append(f"{athlete_name} (owned by {athlete.owner})")
                continue

            username = self._username_for_name(athlete_name)
            first_name, last_name = self._split_name(athlete_name)
            user = User.objects.filter(username__iexact=username).first()
            if user and (user.is_staff or user.is_superuser):
                conflicts.append(f"{athlete_name} (username {username} is staff/admin)")
                continue

            if not user:
                user = User(username=username)
                created.append(username)
            else:
                updated.append(username)

            user.first_name = first_name
            user.last_name = last_name
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.set_password(password)
            user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Owner: {owner.username} | created {len(created)} | updated {len(updated)} | "
                f"missing athletes {len(missing_athletes)} | conflicts {len(conflicts)}"
            )
        )
        if created:
            self.stdout.write("Created users: " + ", ".join(created))
        if updated:
            self.stdout.write("Updated users: " + ", ".join(updated))
        if missing_athletes:
            self.stdout.write(self.style.WARNING("Missing athletes: " + ", ".join(missing_athletes)))
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

    def _split_name(self, name):
        parts = name.split()
        if len(parts) <= 1:
            return name, ""
        return parts[0], " ".join(parts[1:])

    def _username_for_name(self, name):
        return "_".join(name.split())
