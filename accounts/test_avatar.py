from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from capsules.models import PendingFileDeletion
from capsules.storage import private_photo_storage
from capsules.test_photos import image_upload


class ProfileAvatarTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        settings = override_settings(PRIVATE_MEDIA_ROOT=self.root)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = get_user_model().objects.create_user(username="avatar_user")
        self.other = get_user_model().objects.create_user(username="other_avatar", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("accounts:profile")
        self.image_url = reverse("accounts:avatar")
        self.data = {"first_name": "Diana", "last_name": "", "timezone": "Europe/Bucharest"}

    def upload(self, image=None):
        return self.client.post(self.url, {**self.data, "avatar_upload": image or image_upload()})

    def test_default_avatar_and_upload_control_are_under_profile_heading(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'aria-label="Avatar implicit"')
        self.assertContains(response, 'form="profile-form"')
        self.assertContains(response, 'id="profile-form" method="post" enctype="multipart/form-data"')
        self.assertContains(response, 'name="avatar_upload"')
        self.assertEqual(self.client.get(self.image_url).status_code, 404)

    def test_supported_images_are_normalized_to_private_png_and_resized_proportionally(self):
        for fmt in ("PNG", "JPEG", "WEBP"):
            with self.subTest(fmt=fmt), self.captureOnCommitCallbacks(execute=True):
                self.assertRedirects(self.upload(image_upload(fmt, size=(1024, 512))), self.url)
                self.user.refresh_from_db()
                self.assertTrue(self.user.avatar.name.startswith(f"avatars/{self.user.pk}/"))
                with self.assertRaises(ValueError):
                    _ = self.user.avatar.url
                response = self.client.get(self.image_url)
                self.assertEqual(response["Content-Type"], "image/png")
                self.assertIn("no-store", response["Cache-Control"])
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                with Image.open(BytesIO(b"".join(response.streaming_content))) as decoded:
                    self.assertEqual(decoded.format, "PNG")
                    self.assertEqual(decoded.size, (512, 256))
        self.assertEqual(len(list(self.root.rglob("*.png"))), 1)

    def test_invalid_image_or_invalid_profile_does_not_change_avatar_or_names(self):
        self.upload()
        self.user.refresh_from_db()
        original = self.user.avatar.name
        for changes in (
            {"avatar_upload": SimpleUploadedFile("bad.png", b"not an image"), "first_name": "Changed"},
            {"avatar_upload": image_upload(), "timezone": "invalid", "first_name": "Changed"},
        ):
            response = self.client.post(self.url, {**self.data, **changes})
            self.assertTrue(response.context["form"].errors)
            self.user.refresh_from_db()
            self.assertEqual(self.user.avatar.name, original)
            self.assertEqual(self.user.first_name, "Diana")
        self.assertEqual(len(list(self.root.rglob("*.png"))), 1)

    def test_removal_restores_default_and_cleans_old_file_after_commit(self):
        self.upload()
        self.user.refresh_from_db()
        old_name = self.user.avatar.name
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(self.url, {**self.data, "remove_avatar": "on"}), self.url)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)
        self.assertFalse(private_photo_storage.exists(old_name))
        self.assertContains(self.client.get(self.url), 'aria-label="Avatar implicit"')
        self.assertEqual(self.client.get(self.image_url).status_code, 404)

    def test_replacement_cleans_previous_avatar_and_normal_profile_save_preserves_it(self):
        self.upload()
        self.user.refresh_from_db()
        old = self.user.avatar.name
        with self.captureOnCommitCallbacks(execute=True):
            self.upload(image_upload("JPEG"))
        self.user.refresh_from_db()
        new = self.user.avatar.name
        self.assertNotEqual(old, new)
        self.assertFalse(private_photo_storage.exists(old))
        self.client.post(self.url, {**self.data, "avatar": "arbitrary/private/path.png"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar.name, new)
        self.assertTrue(private_photo_storage.exists(new))

    def test_upload_and_removal_together_require_an_unambiguous_choice(self):
        response = self.client.post(self.url, {**self.data, "avatar_upload": image_upload(), "remove_avatar": "on"})
        self.assertTrue(response.context["form"].non_field_errors())
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_avatar_endpoint_is_owner_only_and_get_or_head_only(self):
        self.upload()
        self.client.logout()
        self.assertRedirects(self.client.get(self.image_url), f"{reverse('accounts:login')}?next={self.image_url}")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.image_url, {"user": self.user.pk}).status_code, 404)
        self.assertEqual(self.client.post(self.image_url).status_code, 405)

    def test_failed_replacement_rolls_back_profile_and_cleans_partial_write(self):
        self.upload()
        self.user.refresh_from_db()
        old = self.user.avatar.name
        save = private_photo_storage.save

        def write_then_fail(*args, **kwargs):
            save(*args, **kwargs)
            raise OSError("storage error")

        with patch.object(private_photo_storage, "save", side_effect=write_then_fail):
            with self.captureOnCommitCallbacks(execute=True), self.assertLogs("accounts.views", level="ERROR"):
                response = self.client.post(self.url, {**self.data, "first_name": "Changed", "avatar_upload": image_upload()})
        self.assertTrue(response.context["form"].non_field_errors())
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Diana")
        self.assertEqual(self.user.avatar.name, old)
        self.assertTrue(private_photo_storage.exists(old))
        self.assertEqual(len(list(self.root.rglob("*.png"))), 1)

    def test_account_deletion_cleans_avatar_and_failed_cleanup_can_be_retried(self):
        self.upload()
        self.user.refresh_from_db()
        name = self.user.avatar.name
        with patch.object(private_photo_storage, "delete", side_effect=OSError("storage unavailable")):
            with self.assertLogs("capsules.photo_services", level="WARNING"), self.captureOnCommitCallbacks(execute=True):
                self.user.delete()
        self.assertTrue(private_photo_storage.exists(name))
        self.assertEqual(PendingFileDeletion.objects.count(), 1)
        call_command("cleanup_private_files", stdout=StringIO())
        self.assertFalse(private_photo_storage.exists(name))

    def test_csrf_is_required_for_upload(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.url, {**self.data, "avatar_upload": image_upload()})
        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)
