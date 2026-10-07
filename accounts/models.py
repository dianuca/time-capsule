from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    timezone = models.CharField(
        max_length=64,
        default="Europe/Bucharest",
    )
    email_notifications_enabled = models.BooleanField(default=True)
