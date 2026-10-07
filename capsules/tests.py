from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_home_page_is_public(self):
        response = self.client.get(reverse("capsules:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "capsules/home.html")
        self.assertContains(response, "Time Capsule") 