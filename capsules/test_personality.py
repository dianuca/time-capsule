from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .admin import CapsuleAdmin
from .forms import CapsuleForm
from .models import Capsule
from .services import DRAFT_FIELDS, seal_capsule, update_draft


class CapsulePersonalityTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="personal")
        self.other = get_user_model().objects.create_user(username="other_personal", is_staff=True)
        self.capsule = Capsule.objects.create(
            owner=self.owner, title="Vacanta la mare", description="Scoici și valuri",
            message="Secretul meu", opens_at=timezone.now() + timedelta(days=30),
        )
        self.seal_url = reverse("capsules:seal", args=[self.capsule.pk])
        self.client.force_login(self.owner)

    def data(self, **changes):
        values = {name: getattr(self.capsule, name) for name in DRAFT_FIELDS}
        values["opens_at"] = self.capsule.opens_at.isoformat()
        return {**values, **changes}

    def test_seal_get_is_confirmation_and_post_seals_once(self):
        response = self.client.get(self.seal_url)
        self.assertContains(response, "Sigilează amintirea")
        self.assertNotContains(response, self.capsule.message)
        self.capsule.refresh_from_db()
        self.assertIsNone(self.capsule.sealed_at)
        response = self.client.post(self.seal_url, follow=True)
        self.assertContains(response, "seal-reveal")
        self.assertNotContains(response, self.capsule.message)
        self.capsule.refresh_from_db()
        first = self.capsule.sealed_at
        self.assertIsNotNone(first)
        self.client.post(self.seal_url)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.sealed_at, first)

    def test_anonymous_and_other_owner_cannot_seal(self):
        self.client.logout()
        for method in (self.client.get, self.client.post):
            self.assertRedirects(method(self.seal_url), f"{reverse('accounts:login')}?next={self.seal_url}")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.seal_url).status_code, 404)
        self.assertEqual(self.client.post(self.seal_url).status_code, 404)
        self.capsule.refresh_from_db()
        self.assertIsNone(self.capsule.sealed_at)

    def test_blank_message_and_expired_date_prevent_seal(self):
        for changes in ({"message": " \n\t "}, {"opens_at": timezone.now() - timedelta(seconds=1)}):
            with self.subTest(changes=changes):
                Capsule.objects.filter(pk=self.capsule.pk).update(**changes)
                response = self.client.post(self.seal_url)
                self.assertContains(response, 'role="alert"')
                self.capsule.refresh_from_db()
                self.assertIsNone(self.capsule.sealed_at)
                Capsule.objects.filter(pk=self.capsule.pk).update(
                    message="Mesaj", opens_at=timezone.now() + timedelta(days=1),
                )

    def test_stale_edit_cannot_overwrite_a_seal(self):
        stale = Capsule.objects.get(pk=self.capsule.pk)
        seal_capsule(self.capsule)
        values = {name: getattr(stale, name) for name in DRAFT_FIELDS}
        values.update(message="Overwrite", theme="green")
        with self.assertRaises(ValidationError):
            update_draft(stale, values)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.message, "Secretul meu")
        self.assertEqual(self.capsule.theme, "lilac")

    def test_stale_seal_rejects_changed_content_and_does_not_seal_blank_message(self):
        stale = Capsule.objects.get(pk=self.capsule.pk)
        values = {name: getattr(stale, name) for name in DRAFT_FIELDS}
        values["message"] = ""
        update_draft(stale, values)
        with self.assertRaises(ValidationError):
            seal_capsule(stale)
        self.capsule.refresh_from_db()
        self.assertIsNone(self.capsule.sealed_at)

    def test_sealed_capsule_cannot_be_edited_including_theme(self):
        seal_capsule(self.capsule)
        response = self.client.post(reverse("capsules:edit", args=[self.capsule.pk]), self.data(theme="pink"))
        self.assertEqual(response.status_code, 403)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.theme, "lilac")

    def test_themes_are_validated_and_saved_on_create_and_edit(self):
        for theme in ("lilac", "cream", "pink", "green"):
            with self.subTest(theme=theme):
                response = self.client.post(reverse("capsules:edit", args=[self.capsule.pk]), self.data(theme=theme))
                self.assertRedirects(response, reverse("capsules:list"))
                self.capsule.refresh_from_db()
                self.assertEqual(self.capsule.theme, theme)
        self.assertRedirects(self.client.post(reverse("capsules:create"), self.data(theme="pink")), reverse("capsules:list"))
        self.assertEqual(Capsule.objects.filter(theme="pink").count(), 1)
        form = CapsuleForm(data=self.data(theme="arbitrary-css"))
        self.assertFalse(form.is_valid())
        self.assertIn("theme", form.errors)

    def test_search_combines_with_state_and_never_searches_private_message(self):
        Capsule.objects.create(owner=self.other, title="Vacanta secretă", opens_at=self.capsule.opens_at)
        response = self.client.get(reverse("capsules:list"), {"q": "VACANTA", "state": "draft"})
        self.assertQuerySetEqual(response.context["capsules"], [self.capsule])
        self.assertEqual(response.context["filters"][0]["count"], 1)
        self.assertContains(response, "q=VACANTA")
        self.assertNotContains(response, "Vacanta secretă")
        for query, state, count in (("valuri", "draft", 1), ("Secretul", "all", 0), ("Vacanta", "sealed", 0)):
            with self.subTest(query=query, state=state):
                response = self.client.get(reverse("capsules:list"), {"q": query, "state": state})
                self.assertEqual(len(response.context["capsules"]), count)

    def test_admin_protects_sealed_content_and_stale_form(self):
        model_admin = CapsuleAdmin(Capsule, admin.site)
        stale = Capsule.objects.get(pk=self.capsule.pk)
        seal_capsule(self.capsule)
        self.capsule.refresh_from_db()
        readonly = model_admin.get_readonly_fields(None, self.capsule)
        self.assertFalse(model_admin.has_change_permission(None, self.capsule))
        for field in DRAFT_FIELDS:
            self.assertIn(field, readonly)
        stale.message = "Admin overwrite"
        with self.assertRaises(PermissionDenied):
            model_admin.save_model(None, stale, None, True)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.message, "Secretul meu")

    def test_csrf_and_method_restrictions_on_seal(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.seal_url).status_code, 403)
        client.get(self.seal_url)
        self.assertEqual(client.post(self.seal_url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value}).status_code, 302)
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.seal_url).status_code, 405)

    def test_edit_view_handles_seal_during_form_validation(self):
        original = CapsuleForm.is_valid

        def validate_then_seal(form):
            valid = original(form)
            seal_capsule(Capsule.objects.get(pk=self.capsule.pk))
            return valid

        with patch.object(CapsuleForm, "is_valid", validate_then_seal):
            response = self.client.post(reverse("capsules:edit", args=[self.capsule.pk]), self.data(message="Târziu"))
        self.assertEqual(response.status_code, 403)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.message, "Secretul meu")
