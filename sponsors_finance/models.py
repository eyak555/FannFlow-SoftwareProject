from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


def validate_benefits(value):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValidationError("Benefits must be a list of strings.")


class Sponsor(models.Model):
    id_sponsor = models.BigAutoField(primary_key=True)
    company_name = models.CharField(max_length=255)
    industry = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=32)
    address = models.TextField()
    target_audience = models.TextField()

    class Meta:
        ordering = ["company_name"]

    def __str__(self):
        return self.company_name


class SponsorshipPackage(models.Model):
    class PackageName(models.TextChoices):
        PLATINUM = "Platinum", "Platinum"
        GOLD = "Gold", "Gold"
        SILVER = "Silver", "Silver"
        BRONZE = "Bronze", "Bronze"

    id_package = models.BigAutoField(primary_key=True)
    package_name = models.CharField(
        max_length=20,
        choices=PackageName.choices,
        unique=True,
    )
    description = models.TextField()
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    benefits = models.JSONField(validators=[validate_benefits])

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return self.get_package_name_display()


class Partnership(models.Model):
    class Status(models.TextChoices):
        PENDING = "Pending", "Pending"
        ACTIVE = "Active", "Active"
        COMPLETED = "Completed", "Completed"
        CANCELLED = "Cancelled", "Cancelled"

    id_partnership = models.BigAutoField(primary_key=True)
    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.PROTECT,
        related_name="partnerships",
    )
    event = models.ForeignKey(
        "events_program.Event",
        on_delete=models.PROTECT,
        related_name="partnerships",
    )
    package = models.ForeignKey(
        SponsorshipPackage,
        on_delete=models.PROTECT,
        related_name="partnerships",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    class Meta:
        ordering = ["-start_date", "sponsor"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="partnership_amount_positive",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="partnership_end_on_or_after_start",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "The negotiated amount must be positive."
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "The end date cannot be earlier than the start date."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.sponsor} — {self.event} ({self.get_status_display()})"


class Budget(models.Model):
    id_budget = models.BigAutoField(primary_key=True)
    event = models.OneToOneField(
        "events_program.Event",
        on_delete=models.PROTECT,
        related_name="budget",
    )
    planned_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(planned_amount__gt=0),
                name="budget_planned_amount_positive",
            ),
        ]

    def clean(self):
        super().clean()
        if self.planned_amount is not None and self.planned_amount <= 0:
            raise ValidationError({"planned_amount": "The planned amount must be positive."})

    def __str__(self):
        return f"Budget for {self.event}"


class Expense(models.Model):
    class Category(models.TextChoices):
        TRANSPORTATION = "Transportation", "Transportation"
        ACCOMMODATION = "Accommodation", "Accommodation"
        CATERING = "Catering", "Catering"
        EQUIPMENT = "Equipment", "Equipment"
        MARKETING = "Marketing", "Marketing"
        DECORATION = "Decoration", "Decoration"
        OTHER = "Other", "Other"

    id_expense = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(
        "events_program.Event",
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    date = models.DateField()
    description = models.TextField()

    class Meta:
        ordering = ["-date", "category"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="expense_amount_positive",
            ),
        ]

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "The expense amount must be positive."})

    def __str__(self):
        return f"{self.get_category_display()} — {self.amount} ({self.event})"
