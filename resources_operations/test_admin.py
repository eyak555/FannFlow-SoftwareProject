from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Resource, ResourceAllocation, Venue
from .tests import create_event


class ResourcesOperationsAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            **{users.USERNAME_FIELD: "admin@example.test"},
            first_name="Admin", last_name="Test",
        )
        create_event(cls.admin, pk=27)
        cls.resource = Resource.objects.create(
            name="Projecteur", type="Éclairage", location="Régie", quantity=10, unit_cost="120.00",
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.start = timezone.localtime().replace(second=0, microsecond=0) + timedelta(days=1)

    def url(self, model, action, *args):
        return reverse(f"admin:resources_operations_{model._meta.model_name}_{action}", args=args)

    def allocation_data(self, quantity=4):
        return {
            "resource": self.resource.pk,
            "event_id": 27,
            "quantity": quantity,
            "start_time": self.start.isoformat(timespec="seconds"),
            "end_time": (self.start + timedelta(hours=2)).isoformat(timespec="seconds"),
        }

    def test_crud_for_all_three_models(self):
        cases = (
            (
                Venue,
                {"name": "Salle des Arts", "type": "Salle", "address": "Tunis", "capacity": 100,
                 "latitude": "0", "longitude": "10", "parking_capacity": 10},
                "capacity", 150,
            ),
            (
                Resource,
                {"name": "Micro", "type": "Son", "location": "Scène", "quantity": 5, "unit_cost": "150.00"},
                "quantity", 7,
            ),
            (ResourceAllocation, self.allocation_data(), "quantity", 6),
        )
        self.assertContains(self.client.get(reverse("admin:index")), "Ressources et opérations")

        for model, data, field, value in cases:
            with self.subTest(model=model.__name__):
                listing = self.url(model, "changelist")
                self.assertContains(self.client.get(self.url(model, "add")), "Enregistrer")
                self.assertRedirects(self.client.post(self.url(model, "add"), data), listing)
                obj = model.objects.latest("pk")

                change = self.url(model, "change", obj.pk)
                self.assertContains(self.client.get(listing), f'href="{change}"')
                details = self.client.get(change)
                self.assertContains(details, str(obj))
                if model is Venue:
                    self.assertContains(details, "mlat=0.000000&amp;mlon=10.000000")
                self.assertRedirects(self.client.post(change, {**data, field: value}), listing)
                obj.refresh_from_db()
                self.assertEqual(getattr(obj, field), value)

                delete = self.url(model, "delete", obj.pk)
                self.assertContains(self.client.get(delete), str(obj))
                self.assertRedirects(self.client.post(delete, {"post": "yes"}), listing)
                self.assertFalse(model.objects.filter(pk=obj.pk).exists())

    def test_admin_preserves_inventory_rules(self):
        add_allocation = self.url(ResourceAllocation, "add")
        self.assertEqual(self.client.post(add_allocation, self.allocation_data(7)).status_code, 302)
        response = self.client.post(add_allocation, self.allocation_data(4))
        self.assertContains(response, "Il reste 3 unité(s) disponible(s)")
        self.assertEqual(ResourceAllocation.objects.count(), 1)

        change = self.url(Resource, "change", self.resource.pk)
        response = self.client.post(change, {
            "name": self.resource.name, "type": self.resource.type, "location": self.resource.location,
            "unit_cost": "120.00", "quantity": 6,
        })
        self.assertContains(response, "nécessitent au moins 7 unité(s)")
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.quantity, 10)

        delete = self.url(Resource, "delete", self.resource.pk)
        self.assertContains(self.client.post(delete, {"post": "yes"}), "protégés")
        self.assertTrue(Resource.objects.filter(pk=self.resource.pk).exists())

    def test_admin_requires_model_permissions(self):
        self.client.logout()
        listing = self.url(Venue, "changelist")
        self.assertRedirects(self.client.get(listing), f"{reverse('admin:login')}?next={listing}")

        users = get_user_model()
        staff = users.objects.create_user(
            email="staff@example.test", first_name="Staff", last_name="Test", role=users.Role.ADMIN,
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(listing).status_code, 403)
        self.assertEqual(self.client.post(self.url(Venue, "add"), {}).status_code, 403)
