from django.contrib.auth.models import AbstractUser
from django.db import models
from capsules.storage import private_photo_storage


def avatar_path(instance, filename):
    return f"avatars/{instance.pk}/{filename}"


class User(AbstractUser):
    avatar = models.FileField(blank=True, storage=private_photo_storage, upload_to=avatar_path, max_length=250)
    timezone = models.CharField(
        max_length=64,
        default="Europe/Bucharest",
    )
    email_notifications_enabled = models.BooleanField(default=True)
