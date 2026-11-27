from django import forms
from django.db.models import Q

from core.forms import FannFlowModelForm
from events_program.models import Event

from .models import Budget, Expense, Partnership, Sponsor, SponsorshipPackage


class SponsorForm(FannFlowModelForm):
    class Meta:
        model = Sponsor
        fields = (
            "company_name",
            "industry",
            "email",
            "phone",
            "address",
            "target_audience",
        )
        labels = {
            "company_name": "Nom de l’entreprise",
            "industry": "Secteur d’activité",
            "email": "Adresse e-mail",
            "phone": "Téléphone",
            "address": "Adresse",
            "target_audience": "Public cible",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
            "address": forms.Textarea(attrs={"rows": 3}),
            "target_audience": forms.Textarea(attrs={"rows": 4}),
        }


class SponsorshipPackageForm(FannFlowModelForm):
    benefits = forms.CharField(
        label="Avantages",
        required=False,
        help_text="Saisissez un avantage par ligne. Chaque ligne sera enregistrée comme une chaîne dans la liste JSON.",
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    class Meta:
        model = SponsorshipPackage
        fields = ("package_name", "description", "price", "benefits")
        labels = {
            "package_name": "Type de forfait",
            "description": "Description",
            "price": "Prix standard",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["benefits"] = "\n".join(self.instance.benefits)

    def clean_benefits(self):
        return [
            line.strip()
            for line in self.cleaned_data["benefits"].splitlines()
            if line.strip()
        ]


class PartnershipForm(FannFlowModelForm):
    class Meta:
        model = Partnership
        fields = (
            "sponsor",
            "event",
            "package",
            "amount",
            "start_date",
            "end_date",
            "status",
        )
        labels = {
            "sponsor": "Sponsor",
            "event": "Événement",
            "package": "Forfait de sponsoring",
            "amount": "Montant négocié",
            "start_date": "Date de début",
            "end_date": "Date de fin",
            "status": "Statut",
        }
        help_texts = {
            "amount": "Montant final convenu avec le sponsor. Il peut différer du prix standard du forfait.",
        }
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.order_by("title")
        self.fields["package"].queryset = SponsorshipPackage.objects.order_by("price")


class BudgetForm(FannFlowModelForm):
    class Meta:
        model = Budget
        fields = ("event", "planned_amount")
        labels = {
            "event": "Événement",
            "planned_amount": "Budget prévisionnel",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        events = Event.objects.filter(budget__isnull=True)
        if self.instance.pk:
            events = Event.objects.filter(
                Q(budget__isnull=True) | Q(pk=self.instance.event_id)
            )
        self.fields["event"].queryset = events.order_by("title")


class ExpenseForm(FannFlowModelForm):
    class Meta:
        model = Expense
        fields = ("event", "category", "amount", "date", "description")
        labels = {
            "event": "Événement",
            "category": "Catégorie",
            "amount": "Montant",
            "date": "Date",
            "description": "Description",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.order_by("title")
