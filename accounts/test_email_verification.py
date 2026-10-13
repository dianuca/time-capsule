import re
import time
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import User, VerifiedEmail


@override_settings(MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}})
class EmailVerificationTests(TestCase):
    def setUp(self):
        self.password = "Private-memory!542"
        self.user = User.objects.create_user("diana", "old@example.com", self.password)
        self.client.force_login(self.user)
        self.url = reverse("accounts:email_settings")
        self.data = {"email": "new@example.com", "password": self.password}

    def send(self, email=None):
        response = self.client.post(self.url, {**self.data, **({"email": email} if email else {})}, secure=True)
        self.assertRedirects(response, reverse("accounts:profile"))
        return re.search(r"https://testserver(\S+)", mail.outbox[-1].body).group(1)

    def claim(self, user=None, email=None):
        user = user or self.user
        return VerifiedEmail.objects.create(user=user, email=email or user.email, verified_at=timezone.now())

    def test_existing_user_starts_unverified_and_keeps_profile_access(self):
        self.assertFalse(self.user.email_is_verified)
        self.assertContains(self.client.get(reverse("accounts:profile")), "Email neconfirmat")

    def test_request_sends_https_link_and_does_not_change_current_email(self):
        link = self.send("NEW@example.com")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")
        self.assertEqual(self.user.pending_email, "new@example.com")
        self.assertFalse(self.user.email_is_verified)
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])
        self.assertIn("diana", mail.outbox[0].body)
        self.assertNotIn(self.password, mail.outbox[0].body)
        self.assertTrue(link.startswith("/accounts/email/confirm/"))

    def test_get_does_not_confirm_and_disables_cache_and_referrer(self):
        response = self.client.get(self.send())
        self.assertTrue(response.context["valid"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertFalse(VerifiedEmail.objects.exists())
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

    def test_confirmation_changes_email_once_and_marks_verified(self):
        link = self.send()
        self.assertRedirects(self.client.post(link), reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertTrue(self.user.email_is_verified)
        self.assertEqual(self.user.pending_email, "")
        self.assertIsNone(self.user.email_verification_nonce)
        self.assertFalse(self.client.get(link).context["valid"])
        self.assertEqual(self.client.post(link).status_code, 200)
        self.assertEqual(VerifiedEmail.objects.count(), 1)

    def test_verifying_existing_address(self):
        self.client.post(self.send(self.user.email))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_is_verified)

    def test_wrong_password_or_invalid_email_does_not_send(self):
        for data in ({**self.data, "password": "wrong"}, {**self.data, "email": "invalid"}):
            response = self.client.post(self.url, data)
            self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_anonymous_requires_login_and_other_user_cannot_confirm(self):
        link = self.send()
        anonymous = Client()
        self.assertEqual(anonymous.get(self.url).status_code, 302)
        self.assertEqual(anonymous.post(link).status_code, 302)
        other = User.objects.create_user("other", "other@example.com")
        anonymous.force_login(other)
        self.assertFalse(anonymous.get(link).context["valid"])
        anonymous.post(link)
        self.assertFalse(VerifiedEmail.objects.exists())

    def test_invalid_and_expired_links(self):
        link = self.send()
        self.assertFalse(self.client.get(link.rstrip("/") + "bad/").context["valid"])
        with patch("django.core.signing.time.time", return_value=time.time() + 3602):
            self.assertFalse(self.client.get(link).context["valid"])
            self.client.post(link)
        self.assertFalse(VerifiedEmail.objects.exists())

    def test_resend_is_throttled_and_new_link_invalidates_old_one(self):
        old = self.send()
        self.assertEqual(self.client.post(self.url, self.data).status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        User.objects.filter(pk=self.user.pk).update(email_verification_sent_at=timezone.now() - timedelta(seconds=61))
        new = self.send()
        self.assertFalse(self.client.get(old).context["valid"])
        self.assertTrue(self.client.get(new).context["valid"])

    def test_delivery_failure_rolls_back_pending_request(self):
        with patch("accounts.email_verification.EmailMessage.send", side_effect=OSError("SMTP unavailable")):
            with self.assertLogs("accounts.views", level="ERROR"):
                response = self.client.post(self.url, self.data)
        self.assertContains(response, "Emailul nu a putut fi trimis")
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verification_nonce)
        self.assertIsNone(self.user.email_verification_sent_at)
        self.send()

    def test_verified_address_cannot_be_claimed_by_other_account(self):
        other = User.objects.create_user("other", "new@example.com")
        self.claim(other)
        response = self.client.post(self.url, self.data)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_duplicate_unverified_accounts_remain_but_only_one_can_claim(self):
        other = User.objects.create_user("duplicate", "new@example.com")
        link = self.send()
        self.claim(other)
        response = self.client.post(link)
        self.assertContains(response, "alt cont")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")
        self.assertFalse(self.user.email_is_verified)
        self.assertEqual(User.objects.count(), 2)

    def test_change_retains_old_verification_until_confirmed_then_releases_address(self):
        self.claim()
        link = self.send()
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_is_verified)
        self.client.post(link)
        self.assertFalse(VerifiedEmail.objects.filter(email="old@example.com").exists())
        self.assertEqual(VerifiedEmail.objects.get(user=self.user).email, "new@example.com")

    def test_out_of_band_email_change_invalidates_old_link_and_verified_status(self):
        self.claim()
        link = self.send()
        User.objects.filter(pk=self.user.pk).update(email="edited@example.com")
        self.assertFalse(self.client.get(link).context["valid"])
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_is_verified)

    def test_csrf_required_for_sending_and_confirming(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.url, self.data).status_code, 403)
        link = self.send()
        self.assertEqual(strict.post(link).status_code, 403)
        self.assertFalse(VerifiedEmail.objects.exists())

    def test_signup_rejects_verified_address_case_insensitively(self):
        self.claim()
        self.client.logout()
        response = self.client.post(reverse("accounts:signup"), {"username": "newuser", "email": "OLD@example.com", "password1": self.password, "password2": self.password})
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_account_deletion_cascades_verified_identity(self):
        self.claim()
        self.user.delete()
        self.assertFalse(VerifiedEmail.objects.exists())
