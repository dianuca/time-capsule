from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from capsules.models import Capsule
from .forms import ProfileForm


User = get_user_model()


class ProfileSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="profile_user", email="profile@example.com", first_name="Diana", last_name="Inițial",
        )
        self.other = User.objects.create_user(username="other_profile", email="other@example.com")
        self.url = reverse("accounts:profile")
        self.client.force_login(self.user)
        self.data = {"first_name": "Dana", "last_name": "Nou", "timezone": "America/New_York", "email_notifications_enabled": "on"}

    def test_anonymous_get_and_post_are_redirected(self):
        self.client.logout()
        for method in (self.client.get, self.client.post):
            response = method(self.url)
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Diana")

    def test_get_prefills_without_mutating_and_is_not_cacheable(self):
        before = User.objects.values().get(pk=self.user.pk)
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "accounts/profile.html")
        self.assertEqual(response.context["form"].initial["timezone"], "Europe/Bucharest")
        self.assertContains(response, 'value="Diana"')
        self.assertContains(response, 'value="Europe/Bucharest" selected')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(User.objects.values().get(pk=self.user.pk), before)

    def test_saves_names_timezone_and_preference_with_success_feedback(self):
        response = self.client.post(self.url, self.data, follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "Preferințele tale au fost salvate.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Dana")
        self.assertEqual(self.user.last_name, "Nou")
        self.assertEqual(self.user.timezone, "America/New_York")
        self.assertTrue(self.user.email_notifications_enabled)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_checkbox_can_be_disabled_and_reenabled(self):
        data = {name: value for name, value in self.data.items() if name != "email_notifications_enabled"}
        self.client.post(self.url, data)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_notifications_enabled)
        self.assertFalse(self.client.get(self.url).context["form"].initial["email_notifications_enabled"])
        self.client.post(self.url, self.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_notifications_enabled)

    def test_invalid_timezone_and_overlong_name_do_not_save_any_fields(self):
        for changes in ({"timezone": "Mars/Olympus"}, {"timezone": ""}, {"timezone": "../../etc/passwd"}, {"first_name": "x" * 151}):
            with self.subTest(changes=changes):
                response = self.client.post(self.url, {**self.data, **changes})
                self.assertTrue(response.context["form"].errors)
                self.user.refresh_from_db()
                self.assertEqual(self.user.first_name, "Diana")
                self.assertEqual(self.user.timezone, "Europe/Bucharest")

    def test_post_cannot_modify_other_user_or_sensitive_fields(self):
        other_before = User.objects.values().get(pk=self.other.pk)
        password = self.user.password
        self.client.post(self.url, {
            **self.data, "id": self.other.pk, "pk": self.other.pk, "username": "hacked",
            "email": "changed@example.com", "password": "hacked", "is_staff": "on", "is_superuser": "on", "is_active": "",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "profile_user")
        self.assertEqual(self.user.email, "profile@example.com")
        self.assertEqual(self.user.password, password)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertTrue(self.user.is_active)
        self.assertEqual(User.objects.values().get(pk=self.other.pk), other_before)

    def test_external_return_urls_are_rejected_and_local_query_is_preserved(self):
        for target in ("https://example.com/", "//example.com/", "javascript:alert(1)", "/\\example.com/"):
            with self.subTest(target=target):
                response = self.client.post(self.url, {**self.data, "next": target})
                self.assertRedirects(response, self.url)
        target = reverse("capsules:list") + "?state=draft&page=2&q=mare"
        self.assertRedirects(self.client.post(self.url, {**self.data, "next": target}), target)

    def test_csrf_is_required_and_unsupported_methods_are_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.data).status_code, 403)
        client.get(self.url)
        response = client.post(self.url, {**self.data, "csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assertRedirects(response, self.url)
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)

    def test_saving_profile_preserves_concurrent_changes_to_sensitive_fields(self):
        original = ProfileForm.is_valid

        def validate_with_concurrent_update(form):
            result = original(form)
            User.objects.filter(pk=self.user.pk).update(email="new@example.com", is_staff=True)
            return result

        with patch.object(ProfileForm, "is_valid", validate_with_concurrent_update):
            self.client.post(self.url, self.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertTrue(self.user.is_staff)
        self.assertEqual(self.user.first_name, "Dana")

    def test_profile_link_displays_escaped_name_in_header(self):
        response = self.client.post(self.url, {**self.data, "first_name": "<script>name</script>"}, follow=True)
        self.assertContains(response, '&lt;script&gt;name&lt;/script&gt; · Profil')
        self.assertNotContains(response, "<script>name</script>")
        self.assertContains(response, f'href="{self.url}"')

    def test_profile_is_a_page_and_account_deletion_remains_a_modal(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="profile-heading"')
        self.assertContains(response, f'class="nav-user" href="{self.url}"')
        self.assertNotContains(response, f'data-capsule-popup href="{self.url}"')
        self.assertContains(response, f'data-capsule-popup href="{reverse("accounts:delete")}"')
        self.assertContains(response, f'name="next" value="{self.url}"')

    def test_timezone_changes_display_and_input_but_not_stored_capsule_moments(self):
        opens_at = datetime(2030, 1, 15, 12, tzinfo=datetime_timezone.utc)
        capsule = Capsule.objects.create(owner=self.user, title="Timezone", message="O scrisoare", opens_at=opens_at)
        self.client.post(self.url, self.data)
        capsule.refresh_from_db()
        self.assertEqual(capsule.opens_at, opens_at)
        self.assertContains(self.client.get(reverse("capsules:list")), "15.01.2030, 07:00")
        edit_url = reverse("capsules:edit", args=[capsule.pk])
        self.assertContains(self.client.get(edit_url), 'value="2030-01-15T07:00"')
        response = self.client.post(edit_url, {"title": "Timezone", "message": "O scrisoare", "opens_at": "2030-01-15T08:00"})
        self.assertRedirects(response, reverse("capsules:list"))
        capsule.refresh_from_db()
        self.assertEqual(capsule.opens_at, datetime(2030, 1, 15, 13, tzinfo=datetime_timezone.utc))

    def test_ambiguous_and_nonexistent_local_dates_are_rejected_after_profile_change(self):
        self.client.post(self.url, {**self.data, "timezone": "Europe/Bucharest"})
        for date in ("2030-03-31T03:30", "2030-10-27T03:30"):
            with self.subTest(date=date):
                response = self.client.post(reverse("capsules:create"), {"title": "DST", "opens_at": date})
                self.assertIn("opens_at", response.context["form"].errors)
        self.assertFalse(Capsule.objects.exists())
