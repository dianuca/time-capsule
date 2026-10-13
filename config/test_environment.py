import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.core.checks import run_checks
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from .environment import boolean, security_settings


# Public test value, never a deployment credential.
PRODUCTION = {
    "DJANGO_DEBUG": "false",
    "DJANGO_SECRET_KEY": "public-test-value-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "DJANGO_ALLOWED_HOSTS": "capsule.example, www.capsule.example",
}


class EnvironmentSettingsTests(SimpleTestCase):
    def test_local_defaults_support_http_loopback_only(self):
        config = security_settings({})
        self.assertTrue(config["DEBUG"])
        self.assertFalse(config["SECURE_SSL_REDIRECT"])
        self.assertFalse(config["SESSION_COOKIE_SECURE"])
        self.assertFalse(config["CSRF_COOKIE_SECURE"])
        self.assertEqual(config["ALLOWED_HOSTS"], ["localhost", "127.0.0.1", "[::1]"])
        self.assertIsNone(config["SECURE_PROXY_SSL_HEADER"])

    def test_booleans_accept_explicit_values_and_reject_typos(self):
        for value in ("true", "1", " YES ", "on"):
            self.assertTrue(boolean({"OPTION": value}, "OPTION", False))
        for value in ("false", "0", " NO ", "off"):
            self.assertFalse(boolean({"OPTION": value}, "OPTION", True))
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_DEBUG"):
            security_settings({"DJANGO_DEBUG": "flase"})

    def test_production_requires_private_strong_key(self):
        for secret in ("", "short", "a" * 64, "django-insecure-" + "test-key-value" * 5):
            with self.subTest(secret_kind=len(secret)):
                with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
                    security_settings({**PRODUCTION, "DJANGO_SECRET_KEY": secret})

    def test_production_requires_explicit_hosts_without_wildcards(self):
        for hosts in ("", " , ", "*", "*.example.com", "https://capsule.example", "capsule.example:443", "capsule.example/path"):
            with self.subTest(hosts=hosts), self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_ALLOWED_HOSTS"):
                security_settings({**PRODUCTION, "DJANGO_ALLOWED_HOSTS": hosts})

    def test_hosts_are_split_and_whitespace_is_ignored(self):
        config = security_settings({**PRODUCTION, "DJANGO_ALLOWED_HOSTS": " capsule.example, , .example.org, [::1] "})
        self.assertEqual(config["ALLOWED_HOSTS"], ["capsule.example", ".example.org", "[::1]"])

    def test_csrf_origins_require_exact_https_origins_in_production(self):
        for origin in ("http://capsule.example", "capsule.example", "https://*.example.com", "https://capsule.example/path", "https://user@capsule.example", "https://@capsule.example", "https://capsule.example:wrong", "https://capsule.example?query=1"):
            with self.subTest(origin=origin), self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_CSRF_TRUSTED_ORIGINS"):
                security_settings({**PRODUCTION, "DJANGO_CSRF_TRUSTED_ORIGINS": origin})
        config = security_settings({**PRODUCTION, "DJANGO_CSRF_TRUSTED_ORIGINS": "https://frontend.example:8443"})
        self.assertEqual(config["CSRF_TRUSTED_ORIGINS"], ["https://frontend.example:8443"])

    def test_hsts_duration_and_proxy_options_are_explicit(self):
        config = security_settings({**PRODUCTION, "DJANGO_HSTS_SECONDS": "7200", "DJANGO_TRUST_PROXY_HEADERS": "true"})
        self.assertEqual(config["SECURE_HSTS_SECONDS"], 7200)
        self.assertEqual(config["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))
        for value in ("-1", "one hour", ""):
            with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_HSTS_SECONDS"):
                security_settings({**PRODUCTION, "DJANGO_HSTS_SECONDS": value})

    def test_real_settings_module_reads_environment(self):
        with patch.dict(os.environ, PRODUCTION, clear=True):
            config = runpy.run_path(str(Path(__file__).with_name("settings.py")), run_name="config._test_settings")
        self.assertFalse(config["DEBUG"])
        self.assertEqual(config["SECRET_KEY"], PRODUCTION["DJANGO_SECRET_KEY"])
        self.assertEqual(config["ALLOWED_HOSTS"], ["capsule.example", "www.capsule.example"])
        self.assertTrue(config["SECURE_SSL_REDIRECT"])
        self.assertTrue(config["SESSION_COOKIE_SECURE"])
        self.assertTrue(config["CSRF_COOKIE_SECURE"])
        self.assertNotEqual(config["STATIC_ROOT"], config["PRIVATE_MEDIA_ROOT"])

    def test_deploy_checks_only_leave_deliberate_hsts_scope_warnings(self):
        with override_settings(**security_settings(PRODUCTION)):
            issues = run_checks(tags=["security"], include_deployment_checks=True)
        self.assertEqual({issue.id for issue in issues}, {"security.W005", "security.W021"})


@override_settings(**security_settings(PRODUCTION))
class ProductionRequestTests(TestCase):
    def test_http_redirects_to_https_without_losing_path_or_query(self):
        response = self.client.get("/accounts/login/?next=/", HTTP_HOST="capsule.example")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "https://capsule.example/accounts/login/?next=/")

    def test_https_has_security_headers_and_secure_csrf_cookie(self):
        response = self.client.get(reverse("accounts:login"), secure=True, HTTP_HOST="capsule.example")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Strict-Transport-Security"], "max-age=3600")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertTrue(response.cookies["csrftoken"]["secure"])

    def test_authenticated_session_cookie_is_secure_and_httponly(self):
        User.objects.create_user("deployment_user", password="Memory-private!542")
        response = self.client.post(reverse("accounts:login"), {"username": "deployment_user", "password": "Memory-private!542"}, secure=True, HTTP_HOST="capsule.example")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.cookies["sessionid"]["secure"])
        self.assertTrue(response.cookies["sessionid"]["httponly"])

    def test_unlisted_host_is_rejected(self):
        self.assertEqual(self.client.get("/", secure=True, HTTP_HOST="attacker.example").status_code, 400)

    def test_forwarded_proto_is_ignored_unless_proxy_trust_is_enabled(self):
        response = self.client.get("/", HTTP_HOST="capsule.example", HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(response.status_code, 301)
        with override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https")):
            response = self.client.get("/", HTTP_HOST="capsule.example", HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Strict-Transport-Security", response)

    def test_untrusted_csrf_origin_is_rejected_but_explicit_origin_is_accepted(self):
        strict = Client(enforce_csrf_checks=True)
        url = reverse("accounts:signup")
        strict.get(url, secure=True, HTTP_HOST="capsule.example")
        token = strict.cookies["csrftoken"].value
        response = strict.post(url, {"csrfmiddlewaretoken": token}, secure=True, HTTP_HOST="capsule.example", HTTP_ORIGIN="https://frontend.example")
        self.assertEqual(response.status_code, 403)
        with override_settings(CSRF_TRUSTED_ORIGINS=["https://frontend.example"]):
            strict = Client(enforce_csrf_checks=True)
            strict.get(url, secure=True, HTTP_HOST="capsule.example")
            token = strict.cookies["csrftoken"].value
            response = strict.post(url, {"csrfmiddlewaretoken": token}, secure=True, HTTP_HOST="capsule.example", HTTP_ORIGIN="https://frontend.example")
        self.assertEqual(response.status_code, 200)
