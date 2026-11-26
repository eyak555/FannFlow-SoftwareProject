from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events_program.models import Event

from .models import Resource, ResourceAllocation, Venue


PASSWORD = "test-resources-2026"


def create_user(name, *, admin=False, director=False, organizer=False):
    users = get_user_model()
    if users._meta.label_lower == "users_teams.user":
        business_role = ""
        if director:
            business_role = users.BusinessRole.DIRECTOR
        if organizer:
            business_role = users.BusinessRole.ORGANIZER
        return users.objects.create_user(
            email=f"{name}@example.test",
            password=PASSWORD,
            first_name=name,
            last_name="Test",
            role=users.Role.ADMIN if admin else users.Role.PARTICIPANT,
            business_role=business_role,
        )

    user = users.objects.create_user(username=name, password=PASSWORD)
    if admin or director:
        group, _ = Group.objects.get_or_create(name="Administrateur" if admin else "Directeur")
        user.groups.add(group)
    return user


def create_event(director, *, pk=None, title="Festival des Arts", capacity=250):
    start = timezone.now() + timedelta(days=2)
    return Event.objects.create(
        pk=pk, title=title, description="Événement de test", event_type=Event.EventType.FESTIVAL,
        start_date=start, end_date=start + timedelta(days=1), registration_deadline=start - timedelta(hours=1),
        capacity=capacity, location="Tunis", director=director,
    )


class ResourceOperationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = create_user("admin-test", admin=True)
        cls.director = create_user("director-test", director=True)
        cls.participant = create_user("participant-test")
        cls.event = create_event(cls.director, pk=27)
        cls.resource = Resource.objects.create(
            name="Éclairage scène", type="Matériel", quantity=10, unit_cost="45.50", location="Entrepôt",
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.start = timezone.localtime().replace(second=0, microsecond=0) + timedelta(days=2)

    def url(self, action, entity, *args):
        return reverse(f"resources_operations:entity_{action}", args=[entity, *args])

    def venue_data(self, **overrides):
        return {
            "name": "Salle des Arts", "type": "Salle", "address": "Tunis",
            "latitude": "0", "longitude": "10.181500", "capacity": 250,
            "surface": "350.50", "parking_capacity": 20, "accessibility": "on",
            **overrides,
        }

    def allocation_data(self, **overrides):
        return {
            "resource": self.resource.pk, "event_id": 27, "quantity": 4,
            "start_time": self.start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_time": (self.start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
            **overrides,
        }

    def test_venue_crud_renders_zero_coordinate_and_confirms_before_delete(self):
        slug = "venues"
        create = self.url("create", slug)
        self.assertContains(self.client.get(create), "Ajouter un lieu")

        response = self.client.post(create, self.venue_data())
        venue = Venue.objects.get()
        detail = self.url("detail", slug, venue.pk)
        self.assertRedirects(response, detail)
        self.assertContains(self.client.get(detail), "mlat=0.000000&amp;mlon=10.181500")

        update = self.url("update", slug, venue.pk)
        response = self.client.post(update, self.venue_data(capacity=275, accessibility=""))
        self.assertRedirects(response, detail)
        venue.refresh_from_db()
        self.assertEqual(venue.capacity, 275)
        self.assertFalse(venue.accessibility)

        delete = self.url("delete", slug, venue.pk)
        self.assertContains(self.client.get(delete), "Salle des Arts")
        self.assertTrue(Venue.objects.filter(pk=venue.pk).exists())
        self.assertRedirects(self.client.post(delete), self.url("list", slug))
        self.assertEqual(self.client.get(detail).status_code, 404)

    def test_venue_validates_coordinate_pair_and_capacity(self):
        response = self.client.post(
            self.url("create", "venues"), self.venue_data(longitude="", capacity=0),
        )
        self.assertFormError(response.context["form"], "longitude", "Renseignez aussi la longitude.")
        self.assertTrue(response.context["form"].has_error("capacity", "min_value"))
        self.assertFalse(Venue.objects.exists())

    def test_resource_crud_uses_exact_decimal_and_lists_empty_stock(self):
        slug = "resources"
        data = {"name": "Micro HF", "type": "Son", "quantity": 4, "unit_cost": "129.95", "location": "Régie"}
        response = self.client.post(self.url("create", slug), data)
        resource = Resource.objects.get(name=data["name"])
        detail = self.url("detail", slug, resource.pk)
        self.assertRedirects(response, detail)
        self.assertEqual(resource.unit_cost, Decimal("129.95"))

        response = self.client.post(self.url("update", slug, resource.pk), {**data, "quantity": 0})
        self.assertRedirects(response, detail)
        response = self.client.get(self.url("list", slug), {"filter": "out-of-stock"})
        self.assertContains(response, "Micro HF")
        self.assertNotContains(response, self.resource.name)
        self.assertRedirects(self.client.post(self.url("delete", slug, resource.pk)), self.url("list", slug))
        self.assertFalse(Resource.objects.filter(pk=resource.pk).exists())

    def test_allocation_crud_displays_event_and_protects_linked_resource(self):
        slug = "resource-allocations"
        response = self.client.post(self.url("create", slug), self.allocation_data())
        allocation = ResourceAllocation.objects.get()
        detail = self.url("detail", slug, allocation.pk)
        self.assertRedirects(response, detail)
        self.assertContains(self.client.get(self.url("list", slug), {"q": "27"}), "Festival des Arts")
        self.assertContains(self.client.get(detail), "#27")
        self.assertEqual(allocation.start_time, self.start)

        update = self.url("update", slug, allocation.pk)
        self.assertContains(self.client.get(update), self.allocation_data()["start_time"])
        self.assertRedirects(self.client.post(update, self.allocation_data(quantity=10)), detail)
        allocation.refresh_from_db()
        self.assertEqual(allocation.quantity, 10)

        resource_delete = self.url("delete", "resources", self.resource.pk)
        self.assertContains(self.client.post(resource_delete), "Supprimez ou réaffectez")
        self.assertTrue(Resource.objects.filter(pk=self.resource.pk).exists())
        self.assertRedirects(self.client.post(self.url("delete", slug, allocation.pk)), self.url("list", slug))
        self.assertRedirects(self.client.post(resource_delete), self.url("list", "resources"))

    def test_allocation_rejects_invalid_time_order(self):
        data = self.allocation_data()
        data["end_time"] = data["start_time"]
        response = self.client.post(self.url("create", "resource-allocations"), data)
        self.assertFormError(response.context["form"], "end_time", "La fin doit être postérieure au début.")
        self.assertFalse(ResourceAllocation.objects.exists())

    def test_availability_uses_peak_concurrent_units_and_allows_touching_slots(self):
        for hour in (0, 1):
            start = self.start + timedelta(hours=hour)
            ResourceAllocation.objects.create(
                resource=self.resource, event_id=hour + 1, quantity=6,
                start_time=start, end_time=start + timedelta(hours=1),
            )

        create = self.url("create", "resource-allocations")
        response = self.client.post(create, self.allocation_data(quantity=5))
        self.assertContains(response, "Il reste 4 unité(s) disponible(s)")
        self.assertEqual(ResourceAllocation.objects.count(), 2)
        response = self.client.post(create, self.allocation_data(quantity=4))
        self.assertEqual(response.status_code, 302)

        end = self.start + timedelta(hours=2)
        response = self.client.post(create, self.allocation_data(
            quantity=10, start_time=end.isoformat(), end_time=(end + timedelta(hours=1)).isoformat(),
        ))
        self.assertEqual(response.status_code, 302)

    def test_stock_reduction_respects_current_and_future_reservations(self):
        for start, quantity in ((self.start, 7), (self.start - timedelta(days=5), 10)):
            ResourceAllocation.objects.create(
                resource=self.resource, event_id=28, quantity=quantity,
                start_time=start, end_time=start + timedelta(hours=1),
            )
        update = self.url("update", "resources", self.resource.pk)
        data = {
            "name": self.resource.name, "type": self.resource.type, "location": self.resource.location,
            "unit_cost": "45.50", "quantity": 6,
        }
        self.assertContains(self.client.post(update, data), "nécessitent au moins 7 unité(s)")
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.quantity, 10)
        self.assertRedirects(
            self.client.post(update, {**data, "quantity": 7}),
            self.url("detail", "resources", self.resource.pk),
        )

    def test_pagination_preserves_search_and_filter(self):
        Venue.objects.bulk_create(
            Venue(name=f"Scène {index:02d}", address="Tunis", type="Plein air", capacity=100, accessibility=True)
            for index in range(13)
        )
        listing = self.url("list", "venues")
        response = self.client.get(listing, {"q": "Tunis", "filter": "accessible"})
        self.assertContains(response, "?q=Tunis&amp;filter=accessible&amp;page=2")
        response = self.client.get(listing, {"q": "Tunis", "filter": "accessible", "page": 2})
        self.assertContains(response, "Scène 12")
        self.assertNotContains(response, "Scène 00")

    def test_module_access_enforces_roles_on_get_and_post(self):
        home = reverse("resources_operations:home")
        self.assertContains(self.client.get(home), "Ajouter une ressource")
        self.client.force_login(self.director)
        response = self.client.get(home)
        self.assertNotContains(response, "Ajouter une ressource")
        self.assertNotContains(response, f'href="{self.url("list", "resources")}"')
        self.assertContains(response, f'href="{self.url("list", "venues")}"')
        self.assertEqual(self.client.get(self.url("list", "resources")).status_code, 403)
        self.assertEqual(self.client.post(self.url("delete", "resources", self.resource.pk)).status_code, 403)
        self.assertRedirects(
            self.client.post(self.url("create", "venues"), self.venue_data()),
            self.url("detail", "venues", Venue.objects.get().pk),
        )
        self.assertEqual(self.client.post(self.url("create", "resource-allocations"), self.allocation_data()).status_code, 302)

        self.client.force_login(self.participant)
        response = self.client.get(home)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(self.url("create", "venues")).status_code, 403)
        self.client.logout()
        response = self.client.get(home)
        login_name = settings.LOGIN_URL if get_user_model()._meta.label_lower == "users_teams.user" else "resources_operations:login"
        self.assertRedirects(response, f"{reverse(login_name)}?next={home}", fetch_redirect_response=False)

    def test_organizer_cannot_open_resources_module(self):
        if get_user_model()._meta.label_lower != "users_teams.user":
            self.skipTest("Le rôle organisateur nécessite le modèle utilisateur FannFlow.")
        self.client.force_login(create_user("organizer-test", organizer=True))
        response = self.client.get(reverse("resources_operations:home"))
        self.assertEqual(response.status_code, 403)
        for slug in ("venues", "resources", "resource-allocations"):
            with self.subTest(slug=slug):
                listing = self.url("list", slug)
                self.assertNotContains(response, f'href="{listing}"', status_code=403)
                self.assertEqual(self.client.get(listing).status_code, 403)
                self.assertEqual(self.client.post(self.url("create", slug)).status_code, 403)

    def test_module_login_returns_to_the_requested_list(self):
        self.client.logout()
        login = reverse("resources_operations:login")
        listing = self.url("list", "venues")
        self.assertContains(self.client.get(login, {"next": listing}), 'name="next"')
        response = self.client.post(login, {
            "username": self.director.get_username(), "password": PASSWORD, "next": listing,
        })
        self.assertRedirects(response, listing)
        self.assertRedirects(self.client.post(reverse("resources_operations:logout")), login)
        self.assertEqual(self.client.get(listing).status_code, 302)

    def test_module_login_redirects_participant_to_fannflow_home(self):
        login = reverse("resources_operations:login")
        credentials = {"username": self.participant.get_username(), "password": PASSWORD}
        for target in ("", reverse("resources_operations:home"), self.url("list", "venues")):
            with self.subTest(target=target):
                self.client.logout()
                response = self.client.post(login, {**credentials, "next": target})
                self.assertRedirects(response, reverse("core:home"))
