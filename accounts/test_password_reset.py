import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import User


@override_settings(MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}})
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("diana", "diana@example.com", "Original-password!38")
        self.url = reverse("accounts:password_reset")
        self.password = "New-secret-memory!493"

    def link(self, user=None):
        user = user or self.user
        return reverse("accounts:password_reset_confirm", kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        })

    def test_login_links_to_reset_and_pages_render(self):
        self.assertContains(self.client.get(reverse("accounts:login")), self.url)
        for name in ("password_reset", "password_reset_done", "password_reset_complete"):
            self.assertEqual(self.client.get(reverse("accounts:" + name)).status_code, 200)

    def test_known_address_sends_https_link_without_changing_password(self):
        response = self.client.post(self.url, {"email": "DIANA@example.com"}, secure=True)
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertIn("https://testserver/accounts/password/reset/", message.body)
        self.assertNotIn("Original-password", message.body)
        link = re.search(r"https://testserver(\S+)", message.body).group(1)
        self.assertTrue(self.client.get(link, follow=True).context["validlink"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Original-password!38"))

    def test_unknown_address_has_same_confirmation_without_email(self):
        response = self.client.post(self.url, {"email": "unknown@example.com"}, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse("accounts:password_reset_done"), 302)])
        self.assertContains(response, "Dacă există un cont eligibil")
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_and_unusable_accounts_receive_no_email(self):
        self.user.is_active = False
        self.user.save()
        self.client.post(self.url, {"email": self.user.email})
        self.user.is_active = True
        self.user.set_unusable_password()
        self.user.save()
        self.client.post(self.url, {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_address_does_not_send(self):
        response = self.client.post(self.url, {"email": "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_changes_password_invalidates_token_and_existing_session(self):
        existing = Client()
        existing.force_login(self.user)
        original = self.link()
        response = self.client.get(original)
        clean_link = response.url
        self.assertIn("set-password", clean_link)
        response = self.client.post(clean_link, {"new_password1": self.password, "new_password2": self.password})
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(Client().get(original).context["validlink"])
        self.assertEqual(existing.get(reverse("accounts:profile")).status_code, 302)

    def test_mismatched_and_weak_passwords_are_rejected(self):
        clean_link = self.client.get(self.link()).url
        for first, second in ((self.password, "different"), ("123", "123")):
            response = self.client.post(clean_link, {"new_password1": first, "new_password2": second})
            self.assertTrue(response.context["form"].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Original-password!38"))

    def test_invalid_and_expired_tokens(self):
        self.assertFalse(self.client.get(self.link().rstrip("/") + "invalid/").context["validlink"])
        token_time = default_token_generator._now()
        link = self.link()
        with patch.object(default_token_generator, "_now", return_value=token_time + timedelta(hours=2)):
            self.assertFalse(self.client.get(link).context["validlink"])

    def test_csrf_required_for_request_and_password_change(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(self.url, {"email": self.user.email}).status_code, 403)
        clean_link = strict.get(self.link()).url
        self.assertEqual(strict.post(clean_link, {"new_password1": self.password, "new_password2": self.password}).status_code, 403)

    def test_untrusted_host_is_rejected(self):
        self.assertEqual(self.client.post(self.url, {"email": self.user.email}, HTTP_HOST="evil.example").status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_duplicate_addresses_keep_existing_accounts_recoverable(self):
        other = User.objects.create_user("other", self.user.email, "Other-original!875")
        self.client.post(self.url, {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Bună, diana!", mail.outbox[0].body)
        self.assertIn("Bună, other!", mail.outbox[1].body)
        self.assertNotEqual(self.link(), self.link(other))
