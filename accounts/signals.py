from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import User
from capsules.photo_services import schedule_file_deletion


@receiver(post_delete, sender=User)
def delete_user_avatar(sender, instance, **kwargs):
    if instance.avatar.name:
        schedule_file_deletion(instance.avatar.name)
