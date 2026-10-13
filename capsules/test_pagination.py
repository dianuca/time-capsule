from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Capsule


class CollectionPaginationTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="pages")
        self.other = get_user_model().objects.create_user(username="other_pages")
        now = timezone.now()
        Capsule.objects.bulk_create([
            Capsule(owner=self.owner, title=f"Amintire {number:02d}", description="mare & cer",
                    message="Mesaj privat", opens_at=now + timedelta(days=30),
                    sealed_at=None if number < 18 else now)
            for number in range(25)
        ])
        Capsule.objects.filter(owner=self.owner).update(created_at=now)
        Capsule.objects.bulk_create([
            Capsule(owner=self.other, title=f"Străină {number}", description="mare & cer", opens_at=now)
            for number in range(15)
        ])
        self.client.force_login(self.owner)
        self.url = reverse("capsules:list")

    def test_pages_are_private_and_have_no_duplicates_when_creation_times_match(self):
        seen = []
        for page, size in ((1, 12), (2, 12), (3, 1)):
            response = self.client.get(self.url, {"page": page})
            items = list(response.context["capsules"])
            self.assertEqual(len(items), size)
            self.assertEqual(response.context["page_obj"].paginator.count, 25)
            self.assertEqual(response.context["page_obj"].number, page)
            self.assertNotContains(response, "Străină")
            self.assertNotContains(response, "Mesaj privat")
            self.assertContains(response, 'data-result-count="25"')
            seen.extend(item.pk for item in items)
        expected = list(Capsule.objects.filter(owner=self.owner).order_by("-created_at", "-pk").values_list("pk", flat=True))
        self.assertEqual(seen, expected)
        self.assertEqual(len(set(seen)), 25)

    def test_links_keep_search_and_filter_and_counts_cover_all_pages(self):
        response = self.client.get(self.url, {"page": 2, "state": "draft", "q": "mare & cer"})
        self.assertEqual(len(response.context["capsules"]), 6)
        self.assertEqual(response.context["page_obj"].paginator.count, 18)
        self.assertEqual([item["count"] for item in response.context["filters"]], [25, 18, 7, 0, 0])
        self.assertContains(response, '?page=1&amp;state=draft&amp;q=mare%20%26%20cer')
        self.assertContains(response, "13–18 din 18 capsule")

    def test_invalid_and_out_of_range_pages_have_safe_fallbacks(self):
        for requested, expected in (("abc", 1), ("100000", 3), ("0", 3), ("-10", 3)):
            with self.subTest(requested=requested):
                response = self.client.get(self.url, {"page": requested})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page_obj"].number, expected)

    def test_empty_results_have_no_pagination_controls(self):
        response = self.client.get(self.url, {"q": "inexistent", "page": 9})
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        self.assertContains(response, 'data-result-count="0"')
        self.assertNotContains(response, 'class="collection-page-link"')
        self.assertContains(response, "Nicio amintire găsită.")

    def test_numbered_navigation_is_elided_for_large_collections(self):
        Capsule.objects.bulk_create([
            Capsule(owner=self.owner, title=f"Extra {index}", opens_at=timezone.now())
            for index in range(120)
        ])
        response = self.client.get(self.url, {"page": 6})
        self.assertContains(response, 'class="page-ellipsis"')
        self.assertContains(response, 'aria-current="page">6')
        self.assertContains(response, 'aria-label="Pagina 13"')
        self.assertNotContains(response, 'aria-label="Pagina 8"')
        self.assertLess(response.content.decode().count('class="collection-page-link"'), 13)

    def test_last_page_falls_back_after_its_only_capsule_is_deleted(self):
        last = self.client.get(self.url, {"page": 3}).context["capsules"][0]
        self.client.post(reverse("capsules:delete", args=[last.pk]))
        response = self.client.get(self.url, {"page": 3})
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["page_obj"].paginator.count, 24)
