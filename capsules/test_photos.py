from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Attachment, Capsule, PendingFileDeletion
from .photo_services import MAX_BYTES, add_photos, remove_photo, validate_photo
from .services import seal_capsule
from .storage import private_photo_storage


def image_upload(fmt="PNG", size=(16, 12), name=None, exif=None):
    output = BytesIO()
    image = Image.new("RGB", size, (100, 120, 150))
    image.save(output, format=fmt, **({"exif": exif} if exif else {}))
    return SimpleUploadedFile(name or f"memory.{fmt.lower()}", output.getvalue(), content_type="application/octet-stream")


class CapsulePhotoTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        settings = override_settings(PRIVATE_MEDIA_ROOT=self.root)
        settings.enable()
        self.addCleanup(settings.disable)
        self.owner = get_user_model().objects.create_user(username="photographer")
        self.other = get_user_model().objects.create_user(username="other_photographer", is_staff=True)
        self.capsule = Capsule.objects.create(
            owner=self.owner, title="Amintiri", message="Scrisoare privată",
            opens_at=timezone.now() + timedelta(days=30),
        )
        self.url = reverse("capsules:photos", args=[self.capsule.pk])
        self.client.force_login(self.owner)

    def upload(self, count=1):
        return self.client.post(self.url, {"photos": [image_upload() for _ in range(count)]})

    def attachment(self):
        add_photos(self.capsule, [validate_photo(image_upload())])
        return self.capsule.attachments.get()

    def image_url(self, attachment):
        return reverse("capsules:image", args=[self.capsule.pk, attachment.pk])

    def delete_url(self, attachment):
        return reverse("capsules:photo-delete", args=[self.capsule.pk, attachment.pk])

    def files(self):
        return [path for path in self.root.rglob("*") if path.is_file()]

    def test_real_supported_formats_are_accepted_and_private(self):
        for fmt, mime in (("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")):
            with self.subTest(fmt=fmt):
                response = self.client.post(self.url, {"photos": image_upload(fmt, name="wrong-extension.txt")})
                self.assertRedirects(response, self.url)
                attachment = self.capsule.attachments.last()
                self.assertEqual(attachment.content_type, mime)
                self.assertEqual((attachment.width, attachment.height), (16, 12))
                self.assertTrue(private_photo_storage.exists(attachment.file.name))
                with self.assertRaises(ValueError):
                    _ = attachment.file.url
                response = self.client.get(self.image_url(attachment))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], mime)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                with Image.open(BytesIO(b"".join(response.streaming_content))) as decoded:
                    self.assertEqual(decoded.format, fmt)

    def test_invalid_disguised_unsupported_and_truncated_files_rejected(self):
        cases = [SimpleUploadedFile("fake.png", b"<svg><script>bad</script></svg>", "image/png"), image_upload("GIF")]
        valid = image_upload().read()
        cases.append(SimpleUploadedFile("broken.png", valid[:30], "image/png"))
        for upload in cases:
            with self.subTest(name=upload.name):
                response = self.client.post(self.url, {"photos": upload})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertFalse(Attachment.objects.exists())
        self.assertEqual(self.files(), [])

    def test_size_and_dimensions_limits(self):
        for upload in (
            SimpleUploadedFile("large.jpg", b"x" * (MAX_BYTES + 1), "image/jpeg"),
            image_upload(size=(12001, 1)),
            image_upload(size=(5001, 5000)),
        ):
            with self.subTest(name=upload.name):
                response = self.client.post(self.url, {"photos": upload})
                self.assertTrue(response.context["form"].errors)
        self.assertFalse(Attachment.objects.exists())

    def test_animated_images_are_rejected(self):
        output = BytesIO()
        first = Image.new("RGB", (8, 8), "red")
        first.save(output, format="PNG", save_all=True, append_images=[Image.new("RGB", (8, 8), "blue")], duration=100)
        with self.assertRaises(ValidationError):
            validate_photo(SimpleUploadedFile("animated.png", output.getvalue()))

    def test_batch_validation_is_all_or_nothing_and_missing_file_shows_error(self):
        response = self.client.post(self.url, {"photos": [image_upload(), SimpleUploadedFile("bad.png", b"bad")]})
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Attachment.objects.exists())
        self.assertEqual(self.files(), [])
        self.assertTrue(self.client.post(self.url).context["form"].errors)

    def test_ten_image_limit_is_per_capsule_and_applies_to_total(self):
        self.assertRedirects(self.upload(10), self.url)
        self.assertEqual(self.capsule.attachments.count(), 10)
        response = self.upload()
        self.assertContains(response, "cel mult 10")
        self.assertEqual(self.capsule.attachments.count(), 10)
        self.assertEqual(len(self.files()), 10)
        response = self.upload(11)
        self.assertTrue(response.context["form"].errors)

    def test_exif_and_appended_payload_are_removed(self):
        exif = Image.Exif()
        exif[270] = "PRIVATE-METADATA"
        upload = image_upload("JPEG", exif=exif)
        upload = SimpleUploadedFile("private.jpg", upload.read() + b"<script>PAYLOAD</script>")
        validated = validate_photo(upload)
        self.assertNotIn(b"PRIVATE-METADATA", validated.data)
        self.assertNotIn(b"PAYLOAD", validated.data)
        with Image.open(BytesIO(validated.data)) as image:
            self.assertFalse(image.getexif())

    def test_owner_preview_and_post_open_gallery_but_no_pre_open_urls(self):
        attachment = self.attachment()
        url = self.image_url(attachment)
        self.assertContains(self.client.get(self.url), url)
        self.capsule.sealed_at = timezone.now()
        self.capsule.save()
        detail = reverse("capsules:detail", args=[self.capsule.pk])
        self.assertNotContains(self.client.get(detail), url)
        self.assertNotContains(self.client.get(detail), 'class="capsule-photo-gallery"')
        self.assertEqual(self.client.get(url).status_code, 403)
        Capsule.objects.filter(pk=self.capsule.pk).update(opens_at=timezone.now() - timedelta(seconds=1))
        self.assertNotContains(self.client.get(detail), url)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.post(detail)
        self.assertContains(self.client.get(detail), url)
        reader = self.client.get(detail)
        self.assertContains(reader, 'class="capsule-photo-gallery"')
        self.assertContains(reader, 'data-gallery-current>1</span>/1')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_anonymous_and_foreign_owner_including_staff_are_denied(self):
        attachment = self.attachment()
        self.client.logout()
        for url, method in ((self.url, "get"), (self.url, "post"), (self.image_url(attachment), "get"), (self.delete_url(attachment), "post")):
            with self.subTest(url=url, method=method):
                self.assertRedirects(getattr(self.client, method)(url), f"{reverse('accounts:login')}?next={url}")
        self.client.force_login(self.other)
        for url, method in ((self.url, "get"), (self.url, "post"), (self.image_url(attachment), "get"), (self.delete_url(attachment), "post")):
            with self.subTest(url=url, method=method):
                self.assertEqual(getattr(self.client, method)(url).status_code, 404)
        self.assertTrue(Attachment.objects.filter(pk=attachment.pk).exists())

    def test_mismatched_capsule_id_and_missing_file_return_404(self):
        attachment = self.attachment()
        for name in ("image", "photo-delete"):
            url = reverse(f"capsules:{name}", args=[uuid4(), attachment.pk])
            response = self.client.get(url) if name == "image" else self.client.post(url)
            self.assertEqual(response.status_code, 404)
        private_photo_storage.delete(attachment.file.name)
        self.assertEqual(self.client.get(self.image_url(attachment)).status_code, 404)

    def test_sealed_upload_and_deletion_rejected_even_with_stale_objects(self):
        attachment = self.attachment()
        stale = Capsule.objects.get(pk=self.capsule.pk)
        seal_capsule(self.capsule)
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url(attachment)).status_code, 403)
        with self.assertRaises(ValidationError):
            add_photos(stale, [validate_photo(image_upload())])
        with self.assertRaises(ValidationError):
            remove_photo(attachment)
        self.assertTrue(Attachment.objects.filter(pk=attachment.pk).exists())
        self.assertEqual(len(self.files()), 1)

    def test_seal_during_upload_validation_prevents_storage_write(self):
        original = validate_photo

        def validate_and_seal(upload):
            result = original(upload)
            seal_capsule(Capsule.objects.get(pk=self.capsule.pk))
            return result

        with patch("capsules.forms.validate_photo", side_effect=validate_and_seal):
            response = self.upload()
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Attachment.objects.exists())
        self.assertEqual(self.files(), [])

    def test_draft_photo_delete_is_post_only_and_cleans_file_after_commit(self):
        attachment = self.attachment()
        url = self.delete_url(attachment)
        self.assertEqual(self.client.get(url).status_code, 405)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(url), self.url)
        self.assertFalse(Attachment.objects.exists())
        self.assertEqual(self.files(), [])
        self.assertFalse(PendingFileDeletion.objects.exists())

    def test_capsule_deletion_cleans_files_in_any_state(self):
        attachment = self.attachment()
        seal_capsule(self.capsule)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("capsules:delete", args=[self.capsule.pk]))
        self.assertRedirects(response, reverse("capsules:list"))
        self.assertFalse(Attachment.objects.exists())
        self.assertFalse(private_photo_storage.exists(attachment.file.name))

    def test_user_cascade_deletion_also_cleans_photos(self):
        self.attachment()
        with self.captureOnCommitCallbacks(execute=True):
            self.owner.delete()
        self.assertEqual(self.files(), [])

    def test_failed_storage_delete_is_queued_and_retry_command_cleans_it(self):
        attachment = self.attachment()
        with patch.object(private_photo_storage, "delete", side_effect=OSError("storage down")):
            with self.assertLogs("capsules.photo_services", level="WARNING"), self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.delete_url(attachment))
        job = PendingFileDeletion.objects.get()
        self.assertEqual(job.attempts, 1)
        self.assertTrue(private_photo_storage.exists(attachment.file.name))
        call_command("cleanup_private_files", stdout=StringIO())
        self.assertFalse(PendingFileDeletion.objects.exists())
        self.assertEqual(self.files(), [])

    def test_rolled_back_deletion_preserves_attachment_and_file(self):
        attachment = self.attachment()
        try:
            with transaction.atomic():
                attachment.delete()
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        self.assertEqual(Attachment.objects.count(), 1)
        self.assertEqual(len(self.files()), 1)
        self.assertFalse(PendingFileDeletion.objects.exists())

    def test_storage_error_after_first_file_rolls_back_batch_and_cleans_files(self):
        real_save = private_photo_storage.save
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            saved = real_save(*args, **kwargs)
            if calls == 2:
                raise OSError("failure after write")
            return saved

        with patch.object(private_photo_storage, "save", side_effect=fail_second):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertLogs("capsules.views", level="ERROR"):
                    response = self.upload(2)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertFalse(Attachment.objects.exists())
        self.assertEqual(self.files(), [])

    def test_mutations_require_csrf_and_files_have_no_public_route(self):
        attachment = self.attachment()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url, {"photos": image_upload()}).status_code, 403)
        self.assertEqual(client.post(self.delete_url(attachment)).status_code, 403)
        client.get(self.url)
        response = client.post(self.url, {
            "photos": image_upload(), "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertRedirects(response, self.url)
        self.assertEqual(self.capsule.attachments.count(), 2)
        self.assertEqual(self.client.get("/private_media/" + attachment.file.name).status_code, 404)
        self.assertEqual(self.client.post(self.image_url(attachment)).status_code, 405)
