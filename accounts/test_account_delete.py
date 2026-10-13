from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from capsules.models import Attachment, Capsule, PendingFileDeletion, Reflection
from capsules.photo_services import add_photos, validate_photo
from capsules.storage import private_photo_storage
from capsules.test_photos import image_upload
from .forms import AccountDeletionForm
from .services import delete_account


User = get_user_model()


class AccountDeletionTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        settings = override_settings(PRIVATE_MEDIA_ROOT=self.root)
        settings.enable()
        self.addCleanup(settings.disable)
        self.password = "Future!Account927"
        self.user = User.objects.create_user(username="delete_account", password=self.password)
        self.other = User.objects.create_user(username="keep_account", is_staff=True)
        now = timezone.now()
        self.capsules = []
        for state in ("draft", "sealed", "opened"):
            capsule = Capsule.objects.create(owner=self.user, title=state, message="PRIVATE ACCOUNT MESSAGE", opens_at=now + timedelta(days=10))
            add_photos(capsule, [validate_photo(image_upload())])
            if state != "draft":
                capsule.sealed_at = now - timedelta(days=30)
                if state == "opened":
                    capsule.opens_at = now - timedelta(days=1)
                    capsule.first_opened_at = now
                capsule.save()
            self.capsules.append(capsule)
        Reflection.objects.create(capsule=self.capsules[-1], changed="PRIVATE REFLECTION")
        self.foreign = Capsule.objects.create(owner=self.other, title="Keep", opens_at=now + timedelta(days=10))
        add_photos(self.foreign, [validate_photo(image_upload())])
        self.url = reverse("accounts:delete")
        self.data = {"password": self.password, "confirm": "on"}
        self.client.force_login(self.user)

    def assert_original_data_exists(self):
        self.assertTrue(User.objects.filter(pk=self.user.pk, is_active=True).exists())
        self.assertEqual(Capsule.objects.filter(owner_id=self.user.pk).count(), 3)
        self.assertEqual(Attachment.objects.filter(capsule__owner_id=self.user.pk).count(), 3)
        self.assertEqual(Reflection.objects.count(), 1)
        self.assertEqual(len([path for path in self.root.rglob("*") if path.is_file()]), 4)

    def test_get_only_confirms_counts_without_exposing_private_contents(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "accounts/account_confirm_delete.html")
        self.assertContains(response, "3 capsule")
        self.assertContains(response, "3 fotografii")
        self.assertContains(response, "1 reflecție")
        self.assertContains(response, "Anulează")
        self.assertNotContains(response, "PRIVATE ACCOUNT MESSAGE")
        self.assertNotContains(response, "PRIVATE REFLECTION")
        self.assertIn("no-store", response["Cache-Control"])
        self.assert_original_data_exists()

    def test_anonymous_get_and_post_are_denied(self):
        self.client.logout()
        for method in (self.client.get, self.client.post):
            response = method(self.url) if method.__name__ == "get" else method(self.url, self.data)
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")
        self.assert_original_data_exists()

    def test_wrong_password_does_not_delete_and_is_never_rendered(self):
        response = self.client.post(self.url, {**self.data, "password": "Wrong!Password927"})
        self.assertIn("password", response.context["form"].errors)
        self.assertNotContains(response, "Wrong!Password927")
        self.assert_original_data_exists()
        self.assertIn("_auth_user_id", self.client.session)

    def test_missing_confirmation_or_password_does_not_delete(self):
        for data, field in (({"password": self.password}, "confirm"), ({"confirm": "on"}, "password")):
            response = self.client.post(self.url, data)
            self.assertIn(field, response.context["form"].errors)
            self.assert_original_data_exists()

    def test_post_deletes_only_current_user_data_and_logs_out(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {**self.data, "user": self.other.pk, "id": self.other.pk}, follow=True)
        self.assertRedirects(response, reverse("capsules:home"))
        self.assertContains(response, "Contul tău a fost șters.")
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Capsule.objects.filter(owner_id=self.user.pk).exists())
        self.assertFalse(Reflection.objects.exists())
        self.assertEqual(Attachment.objects.count(), 1)
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())
        self.assertTrue(Capsule.objects.filter(pk=self.foreign.pk).exists())
        self.assertTrue(private_photo_storage.exists(self.foreign.attachments.get().file.name))
        self.assertFalse(PendingFileDeletion.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_required_and_valid_token_allows_deletion(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.data).status_code, 403)
        self.assert_original_data_exists()
        client.get(self.url)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(self.url, {**self.data, "csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assertRedirects(response, reverse("capsules:home"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_put_patch_and_delete_are_not_accepted(self):
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.url, self.data).status_code, 405)
        self.assert_original_data_exists()

    def test_failed_file_cleanup_is_persisted_and_can_be_retried(self):
        with patch.object(private_photo_storage, "delete", side_effect=OSError("disk unavailable")):
            with self.assertLogs("capsules.photo_services", level="WARNING"), self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url, self.data)
        self.assertRedirects(response, reverse("capsules:home"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(PendingFileDeletion.objects.count(), 3)
        self.assertEqual(Attachment.objects.count(), 1)
        call_command("cleanup_private_files", stdout=StringIO())
        self.assertFalse(PendingFileDeletion.objects.exists())
        self.assertEqual(len([path for path in self.root.rglob("*") if path.is_file()]), 1)

    def test_other_sessions_no_longer_authenticate_deleted_user(self):
        second = Client()
        second.force_login(self.user)
        self.client.post(self.url, self.data)
        response = second.get(reverse("accounts:profile"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('accounts:profile')}")

    def test_database_failure_rolls_back_deactivation_data_and_file_jobs(self):
        original_delete = User.delete

        def delete_then_fail(current, *args, **kwargs):
            original_delete(current, *args, **kwargs)
            raise RuntimeError("rollback after cascade")

        with patch.object(User, "delete", delete_then_fail):
            with self.assertRaises(RuntimeError):
                delete_account(self.user)
        self.assert_original_data_exists()
        self.assertFalse(PendingFileDeletion.objects.exists())

    def test_password_changed_after_validation_prevents_deletion(self):
        original = AccountDeletionForm.is_valid

        def validate_then_change_password(form):
            result = original(form)
            User.objects.filter(pk=self.user.pk).update(password=make_password("Changed!Password927"))
            return result

        with patch.object(AccountDeletionForm, "is_valid", validate_then_change_password):
            response = self.client.post(self.url, self.data)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assert_original_data_exists()

    def test_user_with_unusable_password_cannot_bypass_password_check(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.data)
        self.assertIn("password", response.context["form"].errors)
        self.assert_original_data_exists()
