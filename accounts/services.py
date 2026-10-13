from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from capsules.models import Capsule
from .models import User


def delete_account(user):
    with transaction.atomic():
        # First acquire SQLite's write lock and recheck the validated credential
        # snapshot. PostgreSQL also needs the stronger user row lock below to
        # serialize new capsule FK inserts against cascade collection.
        changed = User.objects.filter(pk=user.pk, password=user.password, is_active=True).update(is_active=False)
        if not changed:
            raise ValidationError("Contul a fost modificat între timp. Autentifică-te din nou înainte de ștergere.")
        current = User.objects.select_for_update().get(pk=user.pk)
        # Uploads, edits and reflections use the same parent capsule write lock.
        Capsule.objects.filter(owner=current).update(updated_at=F("updated_at"))
        current.delete()
