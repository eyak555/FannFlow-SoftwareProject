from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events_program.models import Event
from users_teams.models import User
from sponsors_finance.models import (
    Budget,
    Expense,
    Partnership,
    Sponsor,
    SponsorshipPackage,
)
from sponsors_finance.services import calculate_event_finances


class EventFinancialSummaryTests(TestCase):
    def setUp(self):
        start = timezone.now() + timedelta(days=10)
        self.event = Event.objects.create(
            title="Finance test event",
            description="Event for finance tests",
            event_type=Event.EventType.OTHER,
            start_date=start,
            end_date=start + timedelta(days=1),
            registration_deadline=start - timedelta(days=1),
            capacity=10,
            location="Test venue",
        )

    def test_summary_handles_missing_budget_and_expenses(self):
        summary = calculate_event_finances(self.event)

        self.assertIsNone(summary.planned_budget)
        self.assertEqual(summary.total_expenses, Decimal("0.00"))
        self.assertIsNone(summary.remaining_budget)

    def test_summary_aggregates_expenses_dynamically(self):
        Budget.objects.create(event=self.event, planned_amount=Decimal("1000.00"))
        Expense.objects.create(
            event=self.event,
            category=Expense.Category.CATERING,
            amount=Decimal("125.50"),
            date=timezone.localdate(),
            description="Catering",
        )
        Expense.objects.create(
            event=self.event,
            category=Expense.Category.EQUIPMENT,
            amount=Decimal("74.50"),
            date=timezone.localdate(),
            description="Equipment",
        )

        summary = calculate_event_finances(self.event)

        self.assertEqual(summary.planned_budget, Decimal("1000.00"))
        self.assertEqual(summary.total_expenses, Decimal("200.00"))
        self.assertEqual(summary.remaining_budget, Decimal("800.00"))


class PartnershipValidationTests(TestCase):
    def setUp(self):
        start = timezone.now() + timedelta(days=10)
        self.event = Event.objects.create(
            title="Partnership test event",
            description="Event for partnership tests",
            event_type=Event.EventType.OTHER,
            start_date=start,
            end_date=start + timedelta(days=1),
            registration_deadline=start - timedelta(days=1),
            capacity=10,
            location="Test venue",
        )
        self.sponsor = Sponsor.objects.create(
            company_name="Test Sponsor",
            industry="Technology",
            email="sponsor@example.com",
            phone="+1 555 0100",
            address="1 Test Street",
            target_audience="Developers",
        )
        self.package = SponsorshipPackage.objects.create(
            package_name=SponsorshipPackage.PackageName.GOLD,
            description="Gold package",
            price=Decimal("500.00"),
            benefits=["Logo placement"],
        )

    def test_rejects_end_date_before_start_date(self):
        partnership = Partnership(
            sponsor=self.sponsor,
            event=self.event,
            package=self.package,
            amount=Decimal("400.00"),
            start_date=timezone.localdate(),
            end_date=timezone.localdate() - timedelta(days=1),
        )

        with self.assertRaises(ValidationError):
            partnership.full_clean()


class FinanceFrontendTests(TestCase):
    def setUp(self):
        start = timezone.now() + timedelta(days=10)
        self.event = Event.objects.create(
            title="Frontend finance event",
            description="Event for frontend tests",
            event_type=Event.EventType.OTHER,
            start_date=start,
            end_date=start + timedelta(days=1),
            registration_deadline=start - timedelta(days=1),
            capacity=10,
            location="Test venue",
        )
        self.sponsor = Sponsor.objects.create(
            company_name="Frontend Sponsor",
            industry="Technology",
            email="frontend@example.com",
            phone="+1 555 0100",
            address="1 Test Street",
            target_audience="Developers",
        )
        self.package = SponsorshipPackage.objects.create(
            package_name=SponsorshipPackage.PackageName.GOLD,
            description="Gold package",
            price=Decimal("500.00"),
            benefits=["Logo placement"],
        )
        self.partnership = Partnership.objects.create(
            sponsor=self.sponsor,
            event=self.event,
            package=self.package,
            amount=Decimal("425.00"),
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
        )
        self.budget = Budget.objects.create(
            event=self.event,
            planned_amount=Decimal("1000.00"),
        )
        self.expense = Expense.objects.create(
            event=self.event,
            category=Expense.Category.CATERING,
            amount=Decimal("100.00"),
            date=timezone.localdate(),
            description="Catering",
        )
        self.sponsor_manager = User.objects.create_user(
            email="sponsor-manager@example.com",
            password="test-password",
            first_name="Sam",
            last_name="Sponsor",
            business_role=User.BusinessRole.SPONSOR_MANAGER,
        )
        self.client.force_login(self.sponsor_manager)

    def test_entity_crud_pages_render_with_existing_layout(self):
        entities = {
            "sponsors": self.sponsor,
            "sponsorship-packages": self.package,
            "partnerships": self.partnership,
            "budgets": self.budget,
            "expenses": self.expense,
        }
        for entity, item in entities.items():
            routes = (
                ("entity_list", [entity]),
                ("entity_create", [entity]),
                ("entity_detail", [entity, item.pk]),
                ("entity_update", [entity, item.pk]),
                ("entity_delete", [entity, item.pk]),
            )
            for name, args in routes:
                with self.subTest(entity=entity, route=name):
                    response = self.client.get(
                        reverse(f"sponsors_finance:{name}", args=args)
                    )
                    self.assertEqual(response.status_code, 200)

    def test_sponsor_manager_can_create_sponsor(self):
        response = self.client.post(
            reverse("sponsors_finance:entity_create", args=["sponsors"]),
            {
                "company_name": "New Sponsor",
                "industry": "Arts",
                "email": "new@example.com",
                "phone": "+216 20 000 000",
                "address": "2 Test Street",
                "target_audience": "Artists",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Sponsor.objects.filter(company_name="New Sponsor").exists())

    def test_directors_are_read_only_and_organizers_cannot_access_finance(self):
        director = User.objects.create_user(
            email="director@example.com",
            password="test-password",
            first_name="Dana",
            last_name="Director",
            business_role=User.BusinessRole.DIRECTOR,
        )
        self.client.force_login(director)
        self.assertEqual(
            self.client.get(
                reverse("sponsors_finance:entity_list", args=["sponsors"])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("sponsors_finance:entity_create", args=["sponsors"])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("events_program:home")).status_code,
            200,
        )

        organizer = User.objects.create_user(
            email="organizer@example.com",
            password="test-password",
            first_name="Ollie",
            last_name="Organizer",
            business_role=User.BusinessRole.ORGANIZER,
        )
        self.client.force_login(organizer)
        self.assertEqual(
            self.client.get(
                reverse("sponsors_finance:entity_list", args=["sponsors"])
            ).status_code,
            403,
        )

    def test_sponsor_manager_is_scoped_to_finance_module(self):
        self.assertEqual(
            self.client.get(reverse("sponsors_finance:home")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("events_program:home")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("users_teams:home")).status_code,
            403,
        )
