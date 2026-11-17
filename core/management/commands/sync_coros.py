from django.core.management.base import BaseCommand
from core.coros_sync import sync_due


class Command(BaseCommand):
    help = "Import new FIT activities for due COROS MCP connections."

    def handle(self, *args, **options):
        self.stdout.write(f"Processed {sync_due()} due COROS connection(s).")
