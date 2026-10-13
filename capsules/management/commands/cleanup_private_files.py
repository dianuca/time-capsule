from django.core.management.base import BaseCommand

from capsules.models import PendingFileDeletion
from capsules.photo_services import attempt_file_deletion


class Command(BaseCommand):
    help = "Reîncearcă ștergerea fișierelor private rămase după erori de storage."

    def handle(self, *args, **options):
        deleted = failed = 0
        for pk in PendingFileDeletion.objects.order_by("pk").values_list("pk", flat=True).iterator():
            if attempt_file_deletion(pk):
                deleted += 1
            else:
                failed += 1
        self.stdout.write(f"Fisiere curatate: {deleted}; erori ramase: {failed}.")
