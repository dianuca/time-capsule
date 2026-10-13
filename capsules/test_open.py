from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from capsules.models import Capsule


class CapsuleOpenTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="reader")
        self.other = get_user_model().objects.create_user(username="other_reader", is_staff=True)
        self.now = timezone.now()
        self.capsule = Capsule.objects.create(
            owner=self.owner, title="O scrisoare", message='Privat <script>alert("x")</script>',
            opens_at=self.now, sealed_at=self.now - timedelta(days=30),
        )
        self.url = reverse("capsules:detail", args=[self.capsule.pk])
        self.client.force_login(self.owner)

    def test_anonymous_and_other_owner_are_denied_for_get_and_post(self):
        self.client.logout()
        for method in (self.client.get, self.client.post):
            self.assertRedirects(method(self.url), f"{reverse('accounts:login')}?next={self.url}")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.capsule.refresh_from_db()
        self.assertIsNone(self.capsule.first_opened_at)

    def test_locked_capsule_never_exposes_message_even_with_opened_timestamp(self):
        self.capsule.opens_at = self.now + timedelta(days=1)
        self.capsule.first_opened_at = self.now
        self.capsule.save()
        response = self.client.get(self.url + "?opened=1")
        self.assertNotContains(response, "Privat")
        self.assertContains(response, "Capsula este sigilată")
        self.assertContains(response, "data-opens-at")
        self.assertEqual(self.client.post(self.url).status_code, 403)

    def test_available_get_does_not_open_or_reveal_message(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Deschide scrisoarea")
        self.assertNotContains(response, "Privat")
        self.capsule.refresh_from_db()
        self.assertIsNone(self.capsule.first_opened_at)
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_before_exactly_at_and_after_deadline(self):
        for offset in (-1, 0, 1):
            with self.subTest(offset=offset):
                Capsule.objects.filter(pk=self.capsule.pk).update(first_opened_at=None)
                current = self.now + timedelta(seconds=offset)
                with patch("capsules.views.timezone.now", return_value=current):
                    response = self.client.post(self.url)
                self.capsule.refresh_from_db()
                if offset < 0:
                    self.assertEqual(response.status_code, 403)
                    self.assertIsNone(self.capsule.first_opened_at)
                else:
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(self.capsule.first_opened_at, current)

    def test_repeated_post_preserves_first_open_and_get_reads_escaped_message(self):
        with patch("capsules.views.timezone.now", return_value=self.now):
            response = self.client.post(self.url, follow=True)
        self.assertContains(response, "letter-reveal")
        self.assertContains(response, "Privat &lt;script&gt;")
        self.assertNotContains(response, '<script>alert("x")</script>')
        with patch("capsules.views.timezone.now", return_value=self.now + timedelta(hours=1)):
            self.client.post(self.url)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.first_opened_at, self.now)
        response = self.client.get(self.url)
        self.assertContains(response, "Privat &lt;script&gt;")
        self.assertNotContains(response, "letter-reveal")

    def test_draft_reads_without_marking_open_and_rejects_open_post(self):
        self.capsule.sealed_at = None
        self.capsule.save()
        self.assertContains(self.client.get(self.url), "Privat &lt;script&gt;")
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.capsule.refresh_from_db()
        self.assertIsNone(self.capsule.first_opened_at)

    def test_csrf_is_required_and_other_methods_are_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url).status_code, 403)
        client.get(self.url)
        response = client.post(self.url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assertEqual(response.status_code, 302)
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)

    def test_collection_exposes_open_action_then_read_action(self):
        self.assertContains(self.client.get(reverse("capsules:list")), "Deschide capsula ✉")
        self.client.post(self.url)
        self.assertContains(self.client.get(reverse("capsules:list")), "Citește scrisoarea ↗")
