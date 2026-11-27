from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from events_program.models import Event

from .entities import MODULE
from .forms import (
    BudgetForm,
    ExpenseForm,
    PartnershipForm,
    SponsorForm,
    SponsorshipPackageForm,
)
from .models import Budget, Expense, Partnership, Sponsor, SponsorshipPackage
from .permissions import can_manage_finance
from .services import calculate_event_finances


ENTITY_CONFIG = {
    "sponsors": {
        "model": Sponsor,
        "form": SponsorForm,
        "singular": "Sponsor",
        "plural": "Sponsors",
        "template": "sponsors_finance/sponsors",
        "template_key": "sponsor",
    },
    "sponsorship-packages": {
        "model": SponsorshipPackage,
        "form": SponsorshipPackageForm,
        "singular": "Forfait de sponsoring",
        "plural": "Forfaits de sponsoring",
        "template": "sponsors_finance/packages",
        "template_key": "package",
    },
    "partnerships": {
        "model": Partnership,
        "form": PartnershipForm,
        "singular": "Partenariat",
        "plural": "Partenariats",
        "template": "sponsors_finance/partnerships",
        "template_key": "partnership",
    },
    "budgets": {
        "model": Budget,
        "form": BudgetForm,
        "singular": "Budget",
        "plural": "Budgets",
        "template": "sponsors_finance/budget",
        "template_key": "budget",
    },
    "expenses": {
        "model": Expense,
        "form": ExpenseForm,
        "singular": "Dépense",
        "plural": "Dépenses",
        "template": "sponsors_finance/expenses",
        "template_key": "expense",
    },
}

ACTION_LABELS = {
    "list": "Liste",
    "create": "Création",
    "detail": "Détail",
    "update": "Modification",
    "delete": "Suppression",
}


def module_home(request):
    can_manage = can_manage_finance(request.user)
    return render(
        request,
        "sponsors_finance/home.html",
        {
            "module": MODULE,
            "page_title": MODULE["title"],
            "page_intro": MODULE["summary"],
            "can_manage_finance": can_manage,
            "counts": {
                "sponsors": Sponsor.objects.count(),
                "partnerships": Partnership.objects.count(),
                "packages": SponsorshipPackage.objects.count(),
                "budgets": Budget.objects.count(),
                "expenses": Expense.objects.count(),
            },
            "recent_partnerships": Partnership.objects.select_related(
                "sponsor", "event", "package"
            )[:5],
            "recent_expenses": Expense.objects.select_related("event")[:5],
        },
    )


def _queryset_for(entity):
    model = ENTITY_CONFIG[entity]["model"]
    queryset = model.objects.all()
    if entity == "sponsors":
        return queryset.prefetch_related("partnerships__event", "partnerships__package")
    if entity == "sponsorship-packages":
        return queryset.prefetch_related("partnerships__event", "partnerships__sponsor")
    if entity == "partnerships":
        return queryset.select_related("sponsor", "event", "package")
    if entity == "budgets":
        return queryset.select_related("event")
    if entity == "expenses":
        return queryset.select_related("event")
    return queryset


def _selected_event(request):
    raw_event = request.GET.get("event", "").strip()
    if not raw_event:
        return None
    if not raw_event.isdecimal():
        raise Http404("Événement introuvable.")
    return get_object_or_404(Event, pk=int(raw_event))


def _filter_list(request, entity, queryset):
    search = request.GET.get("q", "").strip()
    selected_event = _selected_event(request) if entity in {"partnerships", "budgets", "expenses"} else None
    selected_category = request.GET.get("category", "")
    selected_status = request.GET.get("status", "")
    selected_industry = request.GET.get("industry", "")
    selected_package = request.GET.get("package", "")

    if search:
        if entity == "sponsors":
            queryset = queryset.filter(
                Q(company_name__icontains=search)
                | Q(industry__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )
        elif entity == "sponsorship-packages":
            queryset = queryset.filter(
                Q(package_name__icontains=search) | Q(description__icontains=search)
            )
        elif entity == "partnerships":
            queryset = queryset.filter(
                Q(sponsor__company_name__icontains=search)
                | Q(event__title__icontains=search)
                | Q(package__package_name__icontains=search)
            )
        elif entity == "budgets":
            queryset = queryset.filter(event__title__icontains=search)
        else:
            queryset = queryset.filter(
                Q(event__title__icontains=search) | Q(description__icontains=search)
            )

    if entity == "sponsors" and selected_industry:
        queryset = queryset.filter(industry=selected_industry)
    if entity == "partnerships":
        if selected_event:
            queryset = queryset.filter(event=selected_event)
        if selected_package.isdecimal():
            queryset = queryset.filter(package_id=int(selected_package))
        if selected_status in Partnership.Status.values:
            queryset = queryset.filter(status=selected_status)
    if entity == "budgets" and selected_event:
        queryset = queryset.filter(event=selected_event)
    if entity == "expenses":
        if selected_event:
            queryset = queryset.filter(event=selected_event)
        if selected_category in Expense.Category.values:
            queryset = queryset.filter(category=selected_category)

    return queryset, {
        "search": search,
        "events": Event.objects.order_by("title"),
        "packages": SponsorshipPackage.objects.order_by("price"),
        "industry_choices": Sponsor.objects.order_by()
        .values_list("industry", flat=True)
        .distinct(),
        "category_choices": Expense.Category.choices,
        "status_choices": Partnership.Status.choices,
        "selected_event": selected_event,
        "selected_category": selected_category,
        "selected_status": selected_status,
        "selected_industry": selected_industry,
        "selected_package": selected_package,
    }


def _object_label(entity, obj):
    if entity == "sponsors":
        return obj.company_name
    if entity == "sponsorship-packages":
        return obj.get_package_name_display()
    if entity == "partnerships":
        return f"{obj.sponsor} — {obj.event}"
    if entity == "budgets":
        return f"Budget — {obj.event}"
    return f"{obj.get_category_display()} — {obj.event}"


def crud_placeholder(request, entity, action, pk=None):
    config = ENTITY_CONFIG.get(entity)
    if config is None or action not in ACTION_LABELS:
        raise Http404("Cette page n’existe pas dans le module.")
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "HEAD", "POST"])

    can_manage = can_manage_finance(request.user)
    if action not in {"list", "detail"} and not can_manage:
        raise PermissionDenied("Vous pouvez consulter les données financières, mais pas les modifier.")

    obj = get_object_or_404(_queryset_for(entity), pk=pk) if pk is not None else None
    base_context = {
        "module": MODULE,
        "entity": next(item for item in MODULE["entities"] if item["slug"] == entity),
        "entity_slug": entity,
        "object": obj,
        "item": obj,
        "can_manage_finance": can_manage,
        "list_url": reverse("sponsors_finance:entity_list", args=[entity]),
        "create_url": reverse("sponsors_finance:entity_create", args=[entity]),
    }

    if action == "list":
        queryset, filters = _filter_list(request, entity, _queryset_for(entity))
        ordering = config["model"]._meta.ordering or ("pk",)
        queryset = queryset.order_by(*ordering)
        page_obj = Paginator(queryset, 20).get_page(request.GET.get("page"))
        base_context.update(
            filters,
            items=page_obj.object_list,
            page_obj=page_obj,
            page_title=config["plural"],
            page_intro=f"Consultez et gérez les {config['plural'].lower()}.",
        )
        if entity == "budgets":
            base_context["budget_rows"] = [
                {
                    "budget": budget,
                    "summary": calculate_event_finances(budget.event),
                }
                for budget in page_obj.object_list
            ]
        return render(
            request,
            f"{config['template']}/{config['template_key']}_list.html",
            base_context,
        )

    if action in {"create", "update"}:
        if action == "update" and obj is None:
            raise Http404("Élément introuvable.")
        initial = {}
        event_id = request.GET.get("event", "")
        if action == "create" and event_id.isdecimal() and entity in {"budgets", "expenses"}:
            initial["event"] = Event.objects.filter(pk=int(event_id)).first()
        form_class = config["form"]
        form = form_class(
            request.POST if request.method == "POST" else None,
            instance=obj,
            initial=initial,
        )
        if request.method == "POST" and form.is_valid():
            saved = form.save()
            verb = "créé" if action == "create" else "modifié"
            messages.success(
                request,
                f"{config['singular']} « {_object_label(entity, saved)} » {verb}.",
            )
            return redirect(
                "sponsors_finance:entity_detail",
                entity=entity,
                pk=saved.pk,
            )

        base_context.update(
            form=form,
            page_title=(
                f"Ajouter {config['singular'].lower()}"
                if action == "create"
                else f"Modifier « {_object_label(entity, obj)} »"
            ),
            page_intro="Les champs marqués d’un astérisque sont obligatoires.",
            cancel_url=(
                reverse("sponsors_finance:entity_detail", args=[entity, obj.pk])
                if obj
                else base_context["list_url"]
            ),
        )
        if entity == "partnerships":
            base_context["package_prices"] = {
                str(package.pk): str(package.price)
                for package in SponsorshipPackage.objects.all()
            }
        return render(
            request,
            f"{config['template']}/{config['template_key']}_form.html",
            base_context,
        )

    if obj is None:
        raise Http404("Élément introuvable.")

    if action == "detail":
        base_context.update(
            page_title=_object_label(entity, obj),
            update_url=reverse("sponsors_finance:entity_update", args=[entity, obj.pk]),
            delete_url=reverse("sponsors_finance:entity_delete", args=[entity, obj.pk]),
        )
        if entity == "budgets":
            summary = calculate_event_finances(obj.event)
            utilization = (
                summary.total_expenses * 100 / summary.planned_budget
                if summary.planned_budget
                else 0
            )
            base_context.update(
                financial_summary=summary,
                utilization_percent=utilization,
            )
        return render(
            request,
            f"{config['template']}/{config['template_key']}_detail.html",
            base_context,
        )

    if action == "delete":
        if request.method == "POST":
            try:
                obj.delete()
            except ProtectedError:
                messages.error(
                    request,
                    f"Impossible de supprimer « {_object_label(entity, obj)} » : des enregistrements liés doivent d’abord être traités.",
                )
                return redirect(
                    "sponsors_finance:entity_detail",
                    entity=entity,
                    pk=obj.pk,
                )
            messages.success(
                request,
                f"{config['singular']} « {_object_label(entity, obj)} » supprimé.",
            )
            return redirect("sponsors_finance:entity_list", entity=entity)
        base_context.update(
            page_title=f"Supprimer {config['singular'].lower()}",
            item_label=_object_label(entity, obj),
            cancel_url=reverse("sponsors_finance:entity_detail", args=[entity, obj.pk]),
        )
        return render(
            request,
            f"{config['template']}/{config['template_key']}_confirm_delete.html",
            base_context,
        )

    raise Http404("Cette page n’existe pas dans le module.")
