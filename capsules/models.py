import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


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