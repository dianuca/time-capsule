from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Capsule, Reflection
from .services import save_reflection


class ReflectionTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="reflector")
        self.other = get_user_model().objects.create_user(username="other_reflector", is_staff=True)
        now = timezone.now()
        self.capsule = Capsule.objects.create(
            owner=self.owner, title="Primul capitol", message="Mesajul original, privat",
            opens_at=now - timedelta(days=1), sealed_at=now - timedelta(days=30),
            first_opened_at=now - timedelta(hours=1), theme="pink",
        )
        self.url = reverse("capsules:reflection", args=[self.capsule.pk])
        self.new_url = reverse("capsules:from-reflection", args=[self.capsule.pk])
        self.detail = reverse("capsules:detail", args=[self.capsule.pk])
        self.data = {"changed": "Am mai mult curaj.", "fulfilled": "Am făcut primul pas.", "surprised": "Oamenii întâlniți."}
        self.client.force_login(self.owner)

    def test_get_shows_questions_without_creating_records(self):
        before = self.capsule.updated_at
        response = self.client.get(self.url)
        self.assertContains(response, "Ce s-a schimbat de atunci?")
        self.assertContains(response, "Ce s-a împlinit?")
        self.assertContains(response, "Ce te-a surprins?")
        self.assertFalse(Reflection.objects.exists())
        self.assertEqual(Capsule.objects.count(), 1)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.updated_at, before)
        self.assertIn("no-store", response["Cache-Control"])

    def test_save_then_edit_preserves_one_reflection_and_original_capsule(self):
        original = Capsule.objects.values().get(pk=self.capsule.pk)
        self.assertRedirects(self.client.post(self.url, self.data), self.detail)
        reflection = Reflection.objects.get()
        created_at = reflection.created_at
        self.assertContains(self.client.get(self.url), self.data["changed"])
        self.assertRedirects(self.client.post(self.url, {**self.data, "changed": "Încă un gând."}), self.detail)
        reflection.refresh_from_db()
        self.assertEqual(Reflection.objects.count(), 1)
        self.assertEqual(reflection.changed, "Încă un gând.")
        self.assertEqual(reflection.created_at, created_at)
        self.assertEqual(Capsule.objects.values().get(pk=self.capsule.pk), original)

    def test_anonymous_and_foreign_owner_are_denied(self):
        self.client.logout()
        for url, method in ((self.url, "get"), (self.url, "post"), (self.new_url, "post")):
            self.assertRedirects(getattr(self.client, method)(url), f"{reverse('accounts:login')}?next={url}")
        self.client.force_login(self.other)
        for url, method in ((self.url, "get"), (self.url, "post"), (self.new_url, "post")):
            self.assertEqual(getattr(self.client, method)(url, self.data).status_code, 404)
        self.assertFalse(Reflection.objects.exists())

    def test_draft_locked_and_unopened_available_capsules_are_blocked(self):
        cases = [
            {"sealed_at": None},
            {"opens_at": timezone.now() + timedelta(days=1)},
            {"first_opened_at": None},
        ]
        original = {name: getattr(self.capsule, name) for name in ("sealed_at", "opens_at", "first_opened_at")}
        for changes in cases:
            with self.subTest(changes=list(changes)):
                Capsule.objects.filter(pk=self.capsule.pk).update(**original)
                Capsule.objects.filter(pk=self.capsule.pk).update(**changes)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
                self.assertEqual(self.client.post(self.new_url).status_code, 403)
        self.assertFalse(Reflection.objects.exists())

    def test_blank_and_overlong_reflections_are_rejected_but_one_answer_is_enough(self):
        for data in ({"changed": " \n "}, {"changed": "x" * 5001}):
            response = self.client.post(self.url, data)
            self.assertTrue(response.context["form"].errors)
            self.assertFalse(Reflection.objects.exists())
        self.assertRedirects(self.client.post(self.url, {"changed": "Un singur gând."}), self.detail)
        self.assertEqual(Reflection.objects.get().fulfilled, "")

    def test_reflection_content_is_escaped_and_not_in_collection(self):
        Reflection.objects.create(capsule=self.capsule, changed='<script>alert("reflection")</script>')
        response = self.client.get(self.detail)
        self.assertContains(response, '&lt;script&gt;alert(&quot;reflection&quot;)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert("reflection")</script>')
        self.assertNotContains(self.client.get(reverse("capsules:list")), 'alert(&quot;reflection&quot;)')
        Capsule.objects.filter(pk=self.capsule.pk).update(opens_at=timezone.now() + timedelta(days=1))
        self.assertNotContains(self.client.get(self.detail), 'alert(&quot;reflection&quot;)')

    def test_new_draft_requires_post_and_existing_reflection_without_creating_on_prepare(self):
        self.assertEqual(self.client.get(self.new_url).status_code, 405)
        self.assertEqual(self.client.post(self.new_url).status_code, 404)
        Reflection.objects.create(capsule=self.capsule, **self.data)
        for _ in range(2):
            response = self.client.post(self.new_url)
            self.assertTemplateUsed(response, "capsules/capsule_form.html")
            self.assertContains(response, f'action="{reverse("capsules:create")}"')
            self.assertContains(response, self.data["changed"])
            self.assertNotContains(response, self.capsule.message)
            self.assertEqual(Capsule.objects.count(), 1)
            self.assertEqual(Reflection.objects.count(), 1)

    def test_prepared_form_can_create_an_independent_draft_only_on_save(self):
        Reflection.objects.create(capsule=self.capsule, **self.data)
        response = self.client.post(self.new_url)
        form = response.context["form"]
        initial = form.initial
        self.assertEqual(initial["theme"], "pink")
        self.assertGreater(initial["opens_at"], timezone.now())
        response = self.client.post(reverse("capsules:create"), {**initial, "opens_at": initial["opens_at"].isoformat()})
        self.assertRedirects(response, reverse("capsules:list"))
        new = Capsule.objects.exclude(pk=self.capsule.pk).get()
        self.assertEqual(new.owner, self.owner)
        self.assertIsNone(new.sealed_at)
        self.assertIsNone(new.first_opened_at)
        self.assertIn(self.data["fulfilled"], new.message)
        self.assertFalse(new.attachments.exists())
        self.assertFalse(Reflection.objects.filter(capsule=new).exists())

    def test_capsule_and_owner_cannot_be_changed_from_post(self):
        foreign = Capsule.objects.create(owner=self.other, title="Străină", opens_at=timezone.now())
        self.client.post(self.url, {**self.data, "capsule": foreign.pk, "owner": self.other.pk})
        self.assertEqual(Reflection.objects.get().capsule, self.capsule)

    def test_service_rechecks_access_and_database_enforces_single_reflection(self):
        Capsule.objects.filter(pk=self.capsule.pk).update(first_opened_at=None)
        with self.assertRaises(ValidationError):
            save_reflection(self.capsule, self.data)
        self.assertFalse(Reflection.objects.exists())
        Reflection.objects.create(capsule=self.capsule, **self.data)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Reflection.objects.create(capsule=self.capsule, **self.data)

    def test_csrf_is_required_for_both_actions(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url, self.data).status_code, 403)
        self.assertEqual(client.post(self.new_url).status_code, 403)
        client.get(self.url)
        token = client.cookies["csrftoken"].value
        self.assertRedirects(client.post(self.url, {**self.data, "csrfmiddlewaretoken": token}), self.detail)
        self.assertEqual(client.post(self.new_url, {"csrfmiddlewaretoken": token}).status_code, 200)
        self.assertEqual(self.client.delete(self.url).status_code, 405)

    def test_deleting_capsule_cascades_reflection(self):
        Reflection.objects.create(capsule=self.capsule, **self.data)
        self.client.post(reverse("capsules:delete", args=[self.capsule.pk]))
        self.assertFalse(Reflection.objects.exists())
