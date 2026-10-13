import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivatePhotoStorage(FileSystemStorage):
    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError("Fotografiile private sunt accesibile doar printr-o rută autorizată.")


private_photo_storage = PrivatePhotoStorage()
