from django.test import Client, TestCase
from django.urls import reverse
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Capsule
from zoneinfo import ZoneInfo
from uuid import uuid4


class CapsuleDeleteTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="delete_owner")
        self.other = User.objects.create_user(username="delete_other")
        self.capsule = Capsule.objects.create(
            owner=self.owner,
            title="Capsula de șters",
            message="Conținut secret care nu trebuie expus",
            opens_at=timezone.now() + timedelta(days=30),
        )
        self.url = reverse("capsules:delete", args=[self.capsule.pk])

    def test_anonymous_get_and_post_redirect_to_login(self):
        for method in (self.client.get, self.client.post):
            with self.subTest(method=method.__name__):
                self.assertRedirects(
                    method(self.url),
                    f"{reverse('accounts:login')}?next={self.url}",
                )
        self.assertTrue(Capsule.objects.filter(pk=self.capsule.pk).exists())

    def test_other_owner_including_staff_receives_404(self):
        self.client.force_login(self.other)
        for staff in (False, True):
            self.other.is_staff = staff
            self.other.save()
            for method in (self.client.get, self.client.post):
                with self.subTest(staff=staff, method=method.__name__):
                    self.assertEqual(method(self.url).status_code, 404)
        self.assertTrue(Capsule.objects.filter(pk=self.capsule.pk).exists())

    def test_get_confirms_without_deleting_or_exposing_locked_message(self):
        self.capsule.sealed_at = timezone.now()
        self.capsule.save()
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "capsules/capsule_confirm_delete.html")
        self.assertContains(response, self.capsule.title)
        self.assertContains(response, "Anulează")
        self.assertContains(response, reverse("capsules:list"))
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertNotContains(response, self.capsule.message)
        self.assertTrue(Capsule.objects.filter(pk=self.capsule.pk).exists())

    def test_owner_can_delete_each_state_and_only_targeted_capsule(self):
        other_capsule = Capsule.objects.create(
            owner=self.other, title="Străină", opens_at=self.capsule.opens_at,
        )
        self.client.force_login(self.owner)
        now = timezone.now()
        for state in ("draft", "locked", "available", "opened"):
            with self.subTest(state=state):
                target = Capsule.objects.create(
                    owner=self.owner, title=state,
                    opens_at=now + timedelta(days=1) if state in ("draft", "locked") else now,
                    sealed_at=None if state == "draft" else now,
                    first_opened_at=now if state == "opened" else None,
                )
                url = reverse("capsules:delete", args=[target.pk])
                listing = self.client.get(reverse("capsules:list"))
                self.assertContains(listing, f'href="{url}"')
                response = self.client.post(url, {"pk": self.capsule.pk}, follow=True)
                self.assertRedirects(response, reverse("capsules:list"))
                self.assertContains(response, "Capsula a fost ștearsă.")
                self.assertFalse(Capsule.objects.filter(pk=target.pk).exists())
                self.assertTrue(Capsule.objects.filter(pk=self.capsule.pk).exists())
                self.assertTrue(Capsule.objects.filter(pk=other_capsule.pk).exists())
                self.assertEqual(self.client.post(url).status_code, 404)

    def test_missing_capsule_returns_404(self):
        self.client.force_login(self.owner)
        url = reverse("capsules:delete", args=[uuid4()])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_unsupported_methods_do_not_delete(self):
        self.client.force_login(self.owner)
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.url).status_code, 405)
        self.assertTrue(Capsule.objects.filter(pk=self.capsule.pk).exists())

    def test_csrf_token_is_required_and_valid_token_allows_deletion(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url).status_code, 403)
        self.assertTrue(Capsule.objects.filter(pk=self.capsule.pk).exists())
        client.get(self.url)
        response = client.post(self.url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assertRedirects(response, reverse("capsules:list"))
        self.assertFalse(Capsule.objects.filter(pk=self.capsule.pk).exists())

class HomePageTests(TestCase):
    def test_home_page_is_public(self):
        response = self.client.get(reverse("capsules:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "capsules/home.html")
        self.assertContains(response, "Time Capsule") 

class CapsuleListTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner")
        self.other_user = User.objects.create_user(username="other")
        self.my_capsule = Capsule.objects.create(
            owner=self.owner,
            title="Capsula mea",
            description="Descrierea mea",
            message="Mesaj privat care nu trebuie afișat",
            opens_at=timezone.now() + timedelta(days=365),
        )
        self.other_capsule = Capsule.objects.create(
            owner=self.other_user,
            title="Capsula altcuiva",
            opens_at=timezone.now() + timedelta(days=365),
        )
        self.url = reverse("capsules:list")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.url)
        login_url = reverse("accounts:login")
        self.assertRedirects(
            response,
            f"{login_url}?next={self.url}",
        )

    def test_user_sees_only_their_capsules(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "capsules/capsule_list.html",
        )
        self.assertQuerySetEqual(
            response.context["capsules"],
            [self.my_capsule],
        )
        self.assertContains(response, self.my_capsule.title)
        self.assertNotContains(response, self.other_capsule.title)

    def test_private_message_is_not_displayed(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, self.my_capsule.description)
        self.assertNotContains(response, self.my_capsule.message)

    def test_user_without_capsules_sees_empty_state(self):
        User = get_user_model()
        new_user = User.objects.create_user(username="new_user")
        self.client.force_login(new_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nu ai încă nicio capsulă.")
        self.assertQuerySetEqual(response.context["capsules"], [])

class CapsuleCreateTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="creator",
            timezone="Europe/Bucharest",
        )
        self.other_user = User.objects.create_user(username="other")
        self.url = reverse("capsules:create")
        local_future = (
            timezone.now() + timedelta(days=30)
        ).astimezone(ZoneInfo(self.user.timezone))
        self.valid_data = {
            "title": "Pentru mine din viitor",
            "description": "O amintire de astăzi",
            "message": "Sper că ai continuat ce ai început.",
            "opens_at": local_future.strftime("%Y-%m-%dT%H:%M"),
        }

    def test_anonymous_user_cannot_create_capsule(self):
        response = self.client.post(self.url, self.valid_data)
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.url}",
        )
        self.assertFalse(Capsule.objects.exists())

    def test_authenticated_user_sees_form(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "capsules/capsule_form.html",
        )

    def test_valid_submission_creates_draft_for_current_user(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.valid_data)
        self.assertRedirects(response, reverse("capsules:list"))
        capsule = Capsule.objects.get()
        self.assertEqual(capsule.owner, self.user)
        self.assertEqual(capsule.title, self.valid_data["title"])
        self.assertEqual(capsule.message, self.valid_data["message"])
        self.assertIsNone(capsule.sealed_at)
        self.assertIsNone(capsule.first_opened_at)

    def test_owner_and_sealing_fields_cannot_be_set_from_post(self):
        self.client.force_login(self.user)
        data = {
            **self.valid_data,
            "owner": self.other_user.pk,
            "sealed_at": self.valid_data["opens_at"],
            "first_opened_at": self.valid_data["opens_at"],
        }
        response = self.client.post(self.url, data)
        self.assertRedirects(response, reverse("capsules:list"))
        capsule = Capsule.objects.get()
        self.assertEqual(capsule.owner, self.user)
        self.assertIsNone(capsule.sealed_at)
        self.assertIsNone(capsule.first_opened_at)

    def test_past_opening_date_is_rejected(self):
        self.client.force_login(self.user)
        local_past = (
            timezone.now() - timedelta(days=1)
        ).astimezone(ZoneInfo(self.user.timezone))
        data = {
            **self.valid_data,
            "opens_at": local_past.strftime("%Y-%m-%dT%H:%M"),
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("opens_at", response.context["form"].errors)
        self.assertFalse(Capsule.objects.exists())

    def test_title_is_required(self):
        self.client.force_login(self.user)
        data = {**self.valid_data, "title": ""}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["form"].errors)
        self.assertFalse(Capsule.objects.exists())

    def test_opening_date_uses_user_timezone(self):
        self.client.force_login(self.user)
        data = {
            **self.valid_data,
            "opens_at": "2030-01-15T12:00",
        }
        response = self.client.post(self.url, data)
        self.assertRedirects(response, reverse("capsules:list"))
        capsule = Capsule.objects.get()
        self.assertEqual(
            capsule.opens_at.isoformat(),
            "2030-01-15T10:00:00+00:00",
        )

class CapsuleEditTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="editor",
            timezone="Europe/Bucharest",
        )
        self.other_user = User.objects.create_user(username="other_editor")
        self.capsule = Capsule.objects.create(
            owner=self.owner,
            title="Titlul inițial",
            description="Descriere inițială",
            message="Mesaj inițial",
            opens_at=timezone.now() + timedelta(days=30),
        )
        self.url = reverse(
            "capsules:edit",
            kwargs={"pk": self.capsule.pk},
        )
        local_date = self.capsule.opens_at.astimezone(
            ZoneInfo(self.owner.timezone)
        )
        self.valid_data = {
            "title": "Titlul modificat",
            "description": "Descriere modificată",
            "message": "Mesaj modificat",
            "opens_at": local_date.strftime("%Y-%m-%dT%H:%M"),
        }

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.post(self.url, self.valid_data)
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.url}",
        )
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Titlul inițial")

    def test_owner_sees_prefilled_form(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "capsules/capsule_form.html",
        )
        self.assertEqual(
            response.context["form"].instance,
            self.capsule,
        )
        self.assertContains(response, "Titlul inițial")
        self.assertContains(response, "Salvează modificările")

    def test_owner_can_update_draft_without_creating_another_capsule(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, self.valid_data)
        self.assertRedirects(response, reverse("capsules:list"))
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Titlul modificat")
        self.assertEqual(self.capsule.message, "Mesaj modificat")
        self.assertEqual(self.capsule.owner, self.owner)
        self.assertEqual(Capsule.objects.count(), 1)

    def test_other_user_cannot_view_or_update_capsule(self):
        self.client.force_login(self.other_user)
        get_response = self.client.get(self.url)
        post_response = self.client.post(self.url, self.valid_data)
        self.assertEqual(get_response.status_code, 404)
        self.assertEqual(post_response.status_code, 404)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Titlul inițial")

    def test_sealed_capsule_cannot_be_viewed_in_editor_or_updated(self):
        self.capsule.sealed_at = timezone.now()
        self.capsule.save()
        self.client.force_login(self.owner)
        get_response = self.client.get(self.url)
        post_response = self.client.post(self.url, self.valid_data)
        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Titlul inițial")

    def test_invalid_date_does_not_change_capsule(self):
        self.client.force_login(self.owner)
        local_past = (
            timezone.now() - timedelta(days=1)
        ).astimezone(ZoneInfo(self.owner.timezone))
        data = {
            **self.valid_data,
            "opens_at": local_past.strftime("%Y-%m-%dT%H:%M"),
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("opens_at", response.context["form"].errors)
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.title, "Titlul inițial")

    def test_owner_cannot_be_changed_through_form(self):
        self.client.force_login(self.owner)
        data = {
            **self.valid_data,
            "owner": self.other_user.pk,
        }
        response = self.client.post(self.url, data)

        self.assertRedirects(response, reverse("capsules:list"))
        self.capsule.refresh_from_db()
        self.assertEqual(self.capsule.owner, self.owner)
