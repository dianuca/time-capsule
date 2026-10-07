from django.test import TestCase
from django.urls import reverse
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Capsule

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

