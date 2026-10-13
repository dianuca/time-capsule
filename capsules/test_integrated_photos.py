from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import CapsuleForm
from .models import Attachment, Capsule, PendingFileDeletion
from .photo_services import add_photos, validate_photo
from .services import seal_capsule
from .storage import private_photo_storage
from .test_photos import image_upload


class IntegratedPhotoFormTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        settings = override_settings(PRIVATE_MEDIA_ROOT=self.root)
        settings.enable()
        self.addCleanup(settings.disable)
        self.owner = get_user_model().objects.create_user(username="integrated")
        self.other = get_user_model().objects.create_user(username="other_integrated")
        self.client.force_login(self.owner)
        self.capsule = Capsule.objects.create(
            owner=self.owner, title="Inițial", message="Mesaj inițial",
            opens_at=timezone.now() + timedelta(days=30),
        )
        self.edit_url = reverse("capsules:edit", args=[self.capsule.pk])
        self.create_url = reverse("capsules:create")

    def data(self, **changes):
        return {
            "title": "Nou", "message": "Noua scrisoare", "description": "Amintiri",
            "theme": "pink", "opens_at": self.capsule.opens_at.isoformat(), **changes,
        }

    def existing_photo(self, capsule=None):
        capsule = capsule or self.capsule
        add_photos(capsule, [validate_photo(image_upload())])
        return capsule.attachments.last()

    def files(self):
        return [file for file in self.root.rglob("*") if file.is_file()]

    def test_create_saves_draft_and_multiple_photos_together(self):
        response = self.client.post(self.create_url, self.data(photos=[image_upload("PNG"), image_upload("JPEG")], owner=self.other.pk))
        self.assertRedirects(response, reverse("capsules:list"))
        created = Capsule.objects.exclude(pk=self.capsule.pk).get()
        self.assertEqual(created.owner, self.owner)
        self.assertEqual(created.message, "Noua scrisoare")
        self.assertEqual(created.theme, "pink")
        self.assertIsNone(created.sealed_at)
        self.assertEqual(created.attachments.count(), 2)
        self.assertEqual(len(self.files()), 2)

    def test_invalid_photo_or_invalid_text_creates_nothing(self):
        for changes in (
            {"photos": SimpleUploadedFile("bad.png", b"bad")},
            {"title": "", "photos": image_upload()},
        ):
            with self.subTest(changes=list(changes)):
                response = self.client.post(self.create_url, self.data(**changes))
                self.assertTrue(response.context["form"].errors)
                self.assertEqual(Capsule.objects.count(), 1)
                self.assertFalse(Attachment.objects.exists())
                self.assertEqual(self.files(), [])

    def test_edit_adds_and_removes_photos_on_same_save(self):
        old = self.existing_photo()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, self.data(photos=image_upload("WEBP"), remove_photos=[str(old.pk)]))
        self.assertRedirects(response, reverse("capsules:list"))
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Nou")
        self.assertFalse(Attachment.objects.filter(pk=old.pk).exists())
        self.assertFalse(private_photo_storage.exists(old.file.name))
        self.assertEqual(self.capsule.attachments.get().content_type, "image/webp")
        self.assertEqual(len(self.files()), 1)

    def test_invalid_edit_keeps_text_and_marked_photos(self):
        old = self.existing_photo()
        response = self.client.post(self.edit_url, self.data(title="", remove_photos=[str(old.pk)]))
        self.assertTrue(response.context["form"].errors)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Inițial")
        self.assertTrue(Attachment.objects.filter(pk=old.pk).exists())
        self.assertTrue(private_photo_storage.exists(old.file.name))
        self.assertTrue(response.context["form"].photo_cards[0]["removed"])

    def test_limit_allows_replacement_at_ten_and_rejects_extra_without_saving_text(self):
        add_photos(self.capsule, [validate_photo(image_upload()) for _ in range(10)])
        response = self.client.post(self.edit_url, self.data(photos=image_upload()))
        self.assertTrue(response.context["form"].non_field_errors())
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Inițial")
        old = self.capsule.attachments.first()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, self.data(photos=image_upload(), remove_photos=[str(old.pk)]))
        self.assertRedirects(response, reverse("capsules:list"))
        self.assertEqual(self.capsule.attachments.count(), 10)
        self.assertEqual(len(self.files()), 10)

    def test_cannot_remove_foreign_capsule_photo_or_supply_removals_at_creation(self):
        foreign = Capsule.objects.create(owner=self.other, title="Străină", opens_at=self.capsule.opens_at)
        photo = self.existing_photo(foreign)
        for url in (self.edit_url, self.create_url):
            response = self.client.post(url, self.data(remove_photos=[str(photo.pk)]))
            self.assertIn("remove_photos", response.context["form"].errors)
        self.assertTrue(Attachment.objects.filter(pk=photo.pk).exists())
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Inițial")

    def test_storage_failure_rolls_back_text_removals_and_new_files(self):
        old = self.existing_photo()
        save = private_photo_storage.save

        def write_then_fail(*args, **kwargs):
            save(*args, **kwargs)
            raise OSError("disk failure")

        with patch.object(private_photo_storage, "save", side_effect=write_then_fail):
            with self.captureOnCommitCallbacks(execute=True), self.assertLogs("capsules.views", level="ERROR"):
                response = self.client.post(self.edit_url, self.data(photos=image_upload(), remove_photos=[str(old.pk)]))
        self.assertTrue(response.context["form"].non_field_errors())
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Inițial")
        self.assertTrue(Attachment.objects.filter(pk=old.pk).exists())
        self.assertTrue(private_photo_storage.exists(old.file.name))
        self.assertEqual(len(self.files()), 1)
        self.assertFalse(PendingFileDeletion.objects.exists())

    def test_storage_failure_during_creation_leaves_no_draft_or_files(self):
        with patch.object(private_photo_storage, "save", side_effect=OSError("disk failure")):
            with self.captureOnCommitCallbacks(execute=True), self.assertLogs("capsules.views", level="ERROR"):
                response = self.client.post(self.create_url, self.data(photos=image_upload()))
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertEqual(Capsule.objects.count(), 1)
        self.assertFalse(Attachment.objects.exists())
        self.assertEqual(self.files(), [])

    def test_seal_during_validation_prevents_all_form_changes(self):
        old = self.existing_photo()
        original = CapsuleForm.is_valid

        def validate_then_seal(form):
            valid = original(form)
            seal_capsule(Capsule.objects.get(pk=self.capsule.pk))
            return valid

        with patch.object(CapsuleForm, "is_valid", validate_then_seal):
            response = self.client.post(self.edit_url, self.data(photos=image_upload(), remove_photos=[str(old.pk)]))
        self.assertEqual(response.status_code, 403)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Inițial")
        self.assertTrue(Attachment.objects.filter(pk=old.pk).exists())
        self.assertEqual(len(self.files()), 1)

    def test_both_forms_render_photo_control_and_collection_has_no_separate_button(self):
        photo = self.existing_photo()
        for url in (self.edit_url, self.create_url):
            response = self.client.get(url)
            self.assertContains(response, 'enctype="multipart/form-data"')
            self.assertContains(response, 'name="photos"')
        response = self.client.get(self.edit_url)
        self.assertContains(response, reverse("capsules:image", args=[self.capsule.pk, photo.pk]))
        self.assertContains(response, 'name="remove_photos"')
        response = self.client.get(reverse("capsules:list"))
        self.assertNotContains(response, reverse("capsules:photos", args=[self.capsule.pk]))
