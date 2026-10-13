from django.contrib.auth.models import AbstractUser
from django.db import models
from capsules.storage import private_photo_storage


def avatar_path(instance, filename):
    return f"avatars/{instance.pk}/{filename}"


class User(AbstractUser):
    pending_email = models.EmailField(blank=True)
    email_verification_nonce = models.UUIDField(null=True, blank=True, editable=False)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    avatar = models.FileField(blank=True, storage=private_photo_storage, upload_to=avatar_path, max_length=250)
    timezone = models.CharField(
        max_length=64,
        default="Europe/Bucharest",
    )
    email_notifications_enabled = models.BooleanField(default=True)

    @property
    def email_is_verified(self):
        return VerifiedEmail.objects.filter(user=self, email=self.email.strip().casefold()).exists()


class VerifiedEmail(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="email_identities")
    email = models.EmailField(unique=True)
    verified_at = models.DateTimeField()
