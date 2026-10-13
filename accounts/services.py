from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from capsules.models import Capsule
from .models import User
from capsules.photo_services import schedule_file_deletion
from capsules.storage import private_photo_storage
from django.core.files.base import ContentFile
from io import BytesIO
from uuid import uuid4
from PIL import Image


def save_profile(user, values, photo=None, remove_avatar=False):
    names = []
    try:
        with transaction.atomic():
            changed = User.objects.filter(pk=user.pk, is_active=True).update(**values)
            if not changed:
                raise ValidationError("Contul nu mai este disponibil. Autentifică-te din nou.")
            current = User.objects.get(pk=user.pk)
            old_name = current.avatar.name
            if photo:
                with Image.open(BytesIO(photo.data)) as image:
                    image.thumbnail((512, 512), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    image.save(output, format="PNG")
                name = f"avatars/{user.pk}/{uuid4().hex}.png"
                if not private_photo_storage.exists(name):
                    names.append(name)
                saved = private_photo_storage.save(name, ContentFile(output.getvalue()))
                if saved != name:
                    names.append(saved)
                User.objects.filter(pk=user.pk).update(avatar=saved)
            elif remove_avatar:
                User.objects.filter(pk=user.pk).update(avatar="")
            if old_name and (photo or remove_avatar):
                schedule_file_deletion(old_name)
    except Exception:
        for name in names:
            schedule_file_deletion(name)
        raise


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
