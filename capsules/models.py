import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from .storage import private_photo_storage


def attachment_path(instance, filename):
    return f"capsules/{instance.capsule_id}/{instance.id}/{filename}"


class Capsule(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="capsules",
    )
    title = models.CharField(max_length=150)
    description = models.CharField(max_length=300, blank=True)
    message = models.TextField(blank=True)
    theme = models.CharField(max_length=8, default="lilac", choices=[
        ("lilac", "Lila"), ("cream", "Crem"), ("pink", "Roz"), ("green", "Verde"),
    ])

    opens_at = models.DateTimeField()
    sealed_at = models.DateTimeField(null=True, blank=True)
    first_opened_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_draft(self):
        return self.sealed_at is None

    @property
    def is_available(self):
        return (
            self.sealed_at is not None
            and timezone.now() >= self.opens_at
        )


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    capsule = models.ForeignKey(Capsule, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(storage=private_photo_storage, upload_to=attachment_path, max_length=250)
    original_name = models.CharField(max_length=150)
    content_type = models.CharField(max_length=20)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class PendingFileDeletion(models.Model):
    name = models.CharField(max_length=250, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
