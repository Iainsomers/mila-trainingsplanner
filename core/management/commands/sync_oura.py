from django.core.management.base import BaseCommand
from core.oura_sync import sync_due


class Command(BaseCommand):
    help = "Process due Oura automatic imports using each athlete's device time zone."

    def handle(self, *args, **options):
        self.stdout.write(f"Processed {sync_due()} due Oura connection(s).")
