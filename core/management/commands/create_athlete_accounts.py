import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import Athlete


class Command(BaseCommand):
    help = "Create or update athlete login accounts from a JSON credentials list."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner",
            required=True,
            help="Coach account username or full name whose athletes receive accounts.",
        )
        parser.add_argument(
            "--credentials-json",
            required=True,
            help='JSON list such as [{"name": "Ada Runner", "password": "secret"}].',
        )

    def handle(self, *args, **options):
        owner = self._find_owner(options["owner"])
        credentials = self._parse_credentials(options["credentials_json"])
        User = get_user_model()
        created = []
        updated = []
        missing_athletes = []
        conflicts = []

        for row in credentials:
            athlete_name = row["name"]
            athlete = Athlete.objects.filter(name__iexact=athlete_name).first()
            if not athlete:
                missing_athletes.append(athlete_name)
                continue
            if athlete.owner_id != owner.id:
                conflicts.append(f"{athlete_name} (owned by {athlete.owner})")
                continue

            username = self._username_for_name(athlete_name)
            user = User.objects.filter(username__iexact=username).first()
            if user and (user.is_staff or user.is_superuser):
                conflicts.append(f"{athlete_name} (username {username} is staff/admin)")
                continue

            if user is None:
                user = User(username=username)
                created.append(username)
            else:
                updated.append(username)

            first_name, last_name = self._split_name(athlete_name)
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.set_password(row["password"])
            user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Owner: {owner.username} | created {len(created)} | updated {len(updated)} | "
                f"missing athletes {len(missing_athletes)} | conflicts {len(conflicts)}"
            )
        )
        if missing_athletes:
            self.stdout.write(self.style.WARNING("Missing athletes: " + ", ".join(missing_athletes)))
        if conflicts:
            self.stdout.write(self.style.WARNING("Conflicts: " + "; ".join(conflicts)))

    def _parse_credentials(self, raw):
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CommandError("--credentials-json must contain valid JSON.") from error

        if not isinstance(rows, list) or not rows:
            raise CommandError("--credentials-json must be a non-empty JSON list.")

        normalized = []
        for row in rows:
            if not isinstance(row, dict):
                raise CommandError("Each credentials entry must be an object with name and password.")
            name = str(row.get("name", "")).strip()
            password = str(row.get("password", ""))
            if not name or not password:
                raise CommandError("Each credentials entry needs a non-empty name and password.")
            normalized.append({"name": name, "password": password})
        return normalized

    def _find_owner(self, value):
        User = get_user_model()
        raw = (value or "").strip()
        candidates = [raw, raw.replace(" ", "_"), raw.replace(" ", "."), raw.replace(" ", "")]
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
        return (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (name, "")

    def _username_for_name(self, name):
        return "_".join(name.split())
