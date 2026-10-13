from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from capsules.models import Capsule


class DemoSeedTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="dianaciodolan")

    def seed(self, **options):
        call_command("seed_demo", stdout=StringIO(), **options)

    def test_seed_creates_valid_and_varied_states(self):
        self.seed()
        self.assertEqual(Capsule.objects.filter(owner=self.owner).count(), 24)
        counts = {"draft": 0, "sealed": 0, "available": 0, "opened": 0}
        for capsule in Capsule.objects.all():
            capsule.full_clean()
            self.assertTrue(timezone.is_aware(capsule.opens_at))
            self.assertLessEqual(capsule.created_at, capsule.opens_at)
            if capsule.is_draft:
                state = "draft"
            elif capsule.first_opened_at:
                state = "opened"
                self.assertLessEqual(capsule.opens_at, capsule.first_opened_at)
                self.assertLessEqual(capsule.first_opened_at, timezone.now())
            else:
                state = "available" if capsule.is_available else "sealed"
            counts[state] += 1
            if capsule.sealed_at:
                self.assertLess(capsule.sealed_at, capsule.opens_at)
        self.assertEqual(counts, dict.fromkeys(counts, 6))
        self.assertTrue(Capsule.objects.filter(message="").exists())
        self.assertTrue(Capsule.objects.filter(description="").exists())

    def test_rerun_preserves_demo_edits_and_existing_data(self):
        existing = Capsule.objects.create(owner=self.owner, title="Personală", opens_at=timezone.now())
        self.seed()
        demo = Capsule.objects.exclude(pk=existing.pk).first()
        demo.title = "Editată manual"
        demo.save()
        before = list(Capsule.objects.order_by("pk").values())
        self.seed()
        self.assertEqual(list(Capsule.objects.order_by("pk").values()), before)

    def test_missing_user_creates_no_data(self):
        with self.assertRaises(CommandError):
            self.seed(username="missing")
        self.assertFalse(Capsule.objects.exists())
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_custom_user_is_isolated_and_private_markup_is_not_leaked(self):
        other = get_user_model().objects.create_user(username="another")
        self.seed(username=other.username)
        self.assertFalse(self.owner.capsules.exists())
        self.assertEqual(other.capsules.count(), 24)
        self.client.force_login(other)
        response = self.client.get(reverse("capsules:list"), {"q": "Ghilimele"})
        self.assertEqual(len(response.context["capsules"]), 1)
        self.assertContains(response, "&lt;b&gt;amintire&lt;/b&gt;")
        self.assertNotContains(response, '<script>alert("demo")</script>')
