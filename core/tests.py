from django.test import TestCase
from django.urls import reverse


class CorePagesTests(TestCase):
    def test_home_page(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Communication &amp; Media", html=True)

    def test_module_placeholder_page(self):
        response = self.client.get(reverse("events_program:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Événement")
