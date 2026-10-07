from django.test import TestCase
from django.urls import reverse
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Capsule
from zoneinfo import ZoneInfo

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

