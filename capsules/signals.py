from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Attachment
from .photo_services import schedule_file_deletion


@receiver(post_delete, sender=Attachment)
def delete_attachment_file(sender, instance, **kwargs):
    if instance.file.name:
        schedule_file_deletion(instance.file.name)
