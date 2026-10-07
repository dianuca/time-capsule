from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class SignUpTests(TestCase):
    def setUp(self):
        self.url = reverse("accounts:signup")
        self.valid_data = {
            "username": "capsule_user",
            "email": "user@example.com",
            "password1": "Future!Letter927",
            "password2": "Future!Letter927",
        }

    def test_signup_page_is_public(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/signup.html")

    def test_valid_signup_creates_user_and_logs_them_in(self):
        response = self.client.post(self.url, self.valid_data)
        self.assertRedirects(response, reverse("capsules:home"))
        user = User.objects.get(username="capsule_user")
        self.assertEqual(user.email, "user@example.com")
        self.assertTrue(user.check_password("Future!Letter927"))
        self.assertEqual(
            self.client.session["_auth_user_id"],
            str(user.pk),
        )

    def test_mismatched_passwords_do_not_create_user(self):
        data = {
            **self.valid_data,
            "password2": "Different!Password384",
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("password2", response.context["form"].errors)
        self.assertFalse(User.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_email_is_required(self):
        data = {**self.valid_data, "email": ""}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(User.objects.exists())

    def test_duplicate_username_is_rejected(self):
        User.objects.create_user(
            username="capsule_user",
            password="Existing!Password384",
        )
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_authenticated_user_is_redirected(self):
        user = User.objects.create_user(
            username="existing_user",
            password="Existing!Password384",
        )
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("capsules:home"))

class AuthenticationTests(TestCase):
    def setUp(self):
        self.password = "Future!Letter927"
        self.user = User.objects.create_user(
            username="test_user",
            email="test@example.com",
            password=self.password,
        )
        self.login_url = reverse("accounts:login")
        self.logout_url = reverse("accounts:logout")

    def test_login_page_is_public(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_valid_login_starts_session(self):
        response = self.client.post(
            self.login_url,
            {
                "username": self.user.username,
                "password": self.password,
            },
        )
        self.assertRedirects(response, reverse("capsules:home"))
        self.assertEqual(
            self.client.session["_auth_user_id"],
            str(self.user.pk),
        )

    def test_wrong_password_does_not_start_session(self):
        response = self.client.post(
            self.login_url,
            {
                "username": self.user.username,
                "password": "Wrong!Password927",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_external_next_url(self):
        response = self.client.post(
            self.login_url,
            {
                "username": self.user.username,
                "password": self.password,
                "next": "https://example.com/",
            },
        )
        self.assertRedirects(response, reverse("capsules:home"))

    def test_authenticated_user_skips_login_page(self):
        self.client.force_login(self.user)
        response = self.client.get(self.login_url)
        self.assertRedirects(response, reverse("capsules:home"))

    def test_post_logout_ends_session(self):
        self.client.force_login(self.user)
        response = self.client.post(self.logout_url)
        self.assertRedirects(response, reverse("capsules:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_get_logout_does_not_end_session(self):
        self.client.force_login(self.user)
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

