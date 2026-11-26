from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max, Q, Sum
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from .entities import MODULE, get_accessible_sections
from .events import planning_events, venue_criteria
from .forms import (
    AllocationPlanningForm, EventRequirementsForm, EventSelectionForm,
    OperationsLoginForm, ResourceAllocationForm, ResourceForm, VenueForm,
)
from .inventory import check_allocation_stock, check_resource_stock, inventory_for_update
from .models import EventRequirements, Resource, ResourceAllocation, Venue
from .pdf import inventory_pdf
from .permissions import can_administer_operations, events_for, is_operations_director
from .planning import allocation_options
from .reports import inventory_report


ENTITIES = {entity["slug"]: entity for entity in MODULE["entities"]}
FORMS = {
    "venues": VenueForm,
    "resources": ResourceForm,
    "resource-allocations": ResourceAllocationForm,
}


class OperationsRoleMixin:
    @cached_property
    def is_admin(self):
        return can_administer_operations(self.request.user)

    @cached_property
    def is_director(self):
        return is_operations_director(self.request.user)


class OperationsLoginView(OperationsRoleMixin, LoginView):
    authentication_form = OperationsLoginForm
    template_name = "resources_operations/login.html"
    next_page = "resources_operations:home"
    extra_context = {"page_title": "Connexion à Resources & Operations"}

    def get_success_url(self):
        destination = super().get_success_url()
        if (
            urlsplit(destination).path.startswith(reverse("resources_operations:home"))
            and not (self.is_admin or self.is_director)
        ):
            return reverse("core:home")
        return destination


class OperationsAccessMixin(OperationsRoleMixin, LoginRequiredMixin, UserPassesTestMixin):
    permission_denied_message = "Votre rôle ne donne pas accès à cette section de Ressources et opérations."

    def get_login_url(self):
        if get_user_model()._meta.label_lower == "users_teams.user":
            return settings.LOGIN_URL
        return reverse("resources_operations:login")

    @cached_property
    def sections(self):
        return get_accessible_sections(self.request.user)

    @cached_property
    def event_scope(self):
        return events_for(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except PermissionDenied:
            return self.handle_no_permission()

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return render(
                self.request,
                "resources_operations/access_denied.html",
                {"page_title": "Accès réservé", "reason": self.get_permission_denied_message()},
                status=403,
            )
        return super().handle_no_permission()

    def test_func(self):
        if "entity" not in self.kwargs:
            return bool(self.sections)
        return any(entity["slug"] == self.kwargs["entity"] for entity in self.sections)

    def check_event_parameter(self, raw):
        if not self.is_admin and raw and len(raw) <= 19 and raw.isascii() and raw.isdecimal():
            self.require_event(int(raw))

    def require_event(self, event_id, *, lock=False):
        events = self.event_scope.select_for_update() if lock else self.event_scope
        if not events.filter(pk=event_id).exists():
            raise PermissionDenied

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["module"] = MODULE
        context["sections"] = self.sections
        context["can_manage_resources"] = any(entity["slug"] == "resources" for entity in self.sections)
        context["show_local_logout"] = get_user_model()._meta.label_lower != "users_teams.user"
        return context


class ModuleHomeView(OperationsAccessMixin, TemplateView):
    template_name = "resources_operations/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = MODULE["title"]
        context["overview"] = [
            {"entity": entity, "count": self.section_count(entity["slug"])}
            for entity in context["sections"]
        ]
        return context

    def section_count(self, slug):
        rows = FORMS[slug]._meta.model.objects.all()
        if slug == "resource-allocations" and not self.is_admin:
            rows = rows.filter(program_event__in=self.event_scope)
        return rows.count()


class EventRequirementsView(OperationsAccessMixin, TemplateView):
    template_name = "resources_operations/event_requirements.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            page_title="Besoins événementiels", events=planning_events(self.event_scope).values(), **kwargs,
        )


class EventRequirementsEditView(OperationsAccessMixin, FormView):
    template_name = "resources_operations/event_requirements_form.html"
    form_class = EventRequirementsForm
    success_url = "resources_operations:event_requirements"

    def get_success_url(self):
        return reverse(self.success_url)

    @cached_property
    def event(self):
        event_id = self.kwargs["event_id"]
        if not self.is_admin:
            self.require_event(event_id)
        return get_object_or_404(self.event_scope, pk=event_id)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        profile = EventRequirements.objects.filter(program_event=self.event).first()
        kwargs["instance"] = profile or EventRequirements(program_event=self.event, name=self.event.title)
        return kwargs

    def get_context_data(self, **kwargs):
        return super().get_context_data(page_title="Besoins événementiels", event=self.event, **kwargs)

    def form_valid(self, form):
        profile = form.save(commit=False)
        try:
            with transaction.atomic():
                self.require_event(self.event.pk, lock=True)
                if profile._state.adding:
                    profile.pk = self.event.pk
                    if EventRequirements.objects.filter(pk=profile.pk).exists():
                        profile.pk = EventRequirements.objects.aggregate(latest=Max("pk"))["latest"] + 1
                profile.name = self.event.title
                profile.save(force_insert=profile._state.adding)
        except IntegrityError:
            if not EventRequirements.objects.filter(Q(pk=profile.pk) | Q(program_event_id=self.event.pk)).exists():
                raise
            form.add_error(None, "Une fiche vient d’être enregistrée. Rechargez-la depuis la liste.")
            return self.form_invalid(form)
        messages.success(self.request, f"Les besoins pour « {profile.name} » ont été enregistrés.")
        return super().form_valid(form)


class AllocationPlanningView(OperationsAccessMixin, TemplateView):
    template_name = "resources_operations/allocation_planning.html"

    def get_context_data(self, **kwargs):
        self.check_event_parameter(self.request.GET.get("event_id"))
        form = AllocationPlanningForm(self.request.GET or None, event_scope=self.event_scope)
        options = None
        event = None
        if form.is_valid():
            data = form.cleaned_data
            event = planning_events(self.event_scope.filter(pk=data["event_id"])).get(data["event_id"])
            options = allocation_options(
                data["resource_type"], data["quantity"], data["start_time"],
                data["end_time"], data["latest_start"],
            )
            create_url = reverse("resources_operations:entity_create", args=["resource-allocations"])
            for option in options:
                query = urlencode({
                    "event_id": data["event_id"], "resource": option["resource"].pk,
                    "quantity": data["quantity"],
                    "start_time": timezone.localtime(option["start"]).strftime("%Y-%m-%dT%H:%M:%S"),
                    "end_time": timezone.localtime(option["end"]).strftime("%Y-%m-%dT%H:%M:%S"),
                })
                option["url"] = f"{create_url}?{query}"
        return super().get_context_data(
            page_title="Optimiser une allocation", form=form, options=options, event=event, **kwargs,
        )


class InventoryReportView(OperationsAccessMixin, TemplateView):
    template_name = "resources_operations/inventory_report.html"

    def test_func(self):
        return self.is_admin

    def get_context_data(self, **kwargs):
        now = timezone.now()
        rows = inventory_report(now)
        return super().get_context_data(
            page_title="Inventaire et prévisions", rows=rows, now=now,
            low_count=sum(row["low"] for row in rows),
            risk_count=sum(row["shortage"] > 0 for row in rows), **kwargs,
        )


class InventoryExportView(InventoryReportView):
    def get(self, request, *args, **kwargs):
        now = timezone.now()
        return FileResponse(
            inventory_pdf(inventory_report(now), now), as_attachment=True, filename="inventaire-fannflow.pdf",
        )


class EntityViewMixin(OperationsAccessMixin):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        slug = kwargs["entity"]
        if slug not in ENTITIES:
            raise Http404("Cette section n’existe pas.")
        self.entity = ENTITIES[slug]
        self.model = FORMS[slug]._meta.model

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.model is ResourceAllocation:
            queryset = queryset.select_related("resource", "program_event")
            if not self.is_admin:
                queryset = queryset.filter(program_event__in=self.event_scope)
        return queryset

    def get_object(self, queryset=None):
        if self.model is not ResourceAllocation or self.is_admin:
            return super().get_object(queryset)
        # Un identifiant d’allocation existant hors du périmètre reçoit un 403.
        allocation = super().get_object(ResourceAllocation.objects.select_related("resource", "program_event"))
        self.require_event(allocation.program_event_id)
        return allocation

    def lock_allocation_scope(self, allocation_id):
        saved = get_object_or_404(ResourceAllocation.objects.select_for_update(), pk=allocation_id)
        if not self.is_admin:
            self.require_event(saved.program_event_id, lock=True)
        return saved

    def get_context_data(self, **kwargs):
        return super().get_context_data(entity=self.entity, now=timezone.now(), **kwargs)

    def entity_url(self, action, **kwargs):
        return reverse(f"resources_operations:entity_{action}", kwargs={"entity": self.entity["slug"], **kwargs})


class EntityListView(EntityViewMixin, ListView):
    template_name = "resources_operations/entity_list.html"
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset()
        self.search = self.request.GET.get("q", "").strip()[:150]
        self.selected_filter = self.request.GET.get("filter", "")
        if self.selected_filter not in dict(self.entity["filters"]):
            self.selected_filter = ""
        self.now = timezone.now()

        if self.model is Venue:
            if self.search:
                queryset = queryset.filter(
                    Q(name__icontains=self.search) | Q(type__icontains=self.search) | Q(address__icontains=self.search)
                )
            if self.selected_filter:
                queryset = queryset.filter(accessibility=self.selected_filter == "accessible")
        elif self.model is Resource:
            if self.search:
                queryset = queryset.filter(
                    Q(name__icontains=self.search) | Q(type__icontains=self.search) | Q(location__icontains=self.search)
                )
            if self.selected_filter == "in-stock":
                queryset = queryset.filter(quantity__gt=0)
            elif self.selected_filter == "out-of-stock":
                queryset = queryset.filter(quantity=0)
            elif self.selected_filter == "maintenance":
                queryset = queryset.filter(status=Resource.Status.MAINTENANCE)
            elif self.selected_filter == "unavailable":
                queryset = queryset.filter(status=Resource.Status.UNAVAILABLE)
        else:
            if self.search:
                criteria = Q(resource__name__icontains=self.search) | Q(program_event__title__icontains=self.search)
                if self.search.isdecimal() and int(self.search) <= 2**63 - 1:
                    criteria |= Q(event_id=int(self.search))
                queryset = queryset.filter(criteria)
            if self.selected_filter == "upcoming":
                queryset = queryset.filter(start_time__gt=self.now)
            elif self.selected_filter == "active":
                queryset = queryset.filter(start_time__lte=self.now, end_time__gt=self.now)
            elif self.selected_filter == "ended":
                queryset = queryset.filter(end_time__lte=self.now)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Le gabarit du module conserve les critères de recherche dans ses liens de pagination.
        context["results_page"] = context.pop("page_obj")
        context.update(
            page_title=self.entity["plural"], search=self.search,
            selected_filter=self.selected_filter, now=self.now,
        )
        return context


class EntityDetailView(EntityViewMixin, DetailView):
    template_name = "resources_operations/entity_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(page_title=str(self.object), **kwargs)
        if self.model is Venue:
            self.check_event_parameter(self.request.GET.get("event_id"))
            form = EventSelectionForm(
                self.request.GET if "event_id" in self.request.GET else None, event_scope=self.event_scope,
            )
            context["event_form"] = form
            if form.is_valid():
                event_id = form.cleaned_data["event_id"]
                event = planning_events(self.event_scope.filter(pk=event_id)).get(event_id)
                if event is not None:
                    context["event"] = event
                    criteria = venue_criteria(self.object, event)
                    context["criteria"] = criteria
                    states = {criterion["status"] for criterion in criteria}
                    context["compatibility"] = (
                        "Incompatible" if "fail" in states else "À vérifier" if "unknown" in states else "Compatible"
                    )
        elif self.model is Resource:
            context["total_used"] = self.object.allocations.aggregate(total=Sum("used_quantity", default=0))["total"]
        return context


class EntitySaveMixin(EntityViewMixin):
    template_name = "resources_operations/entity_form.html"

    def get_form_class(self):
        return FORMS[self.entity["slug"]]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.model is ResourceAllocation:
            if self.request.method == "POST":
                self.check_event_parameter(self.request.POST.get("event_id"))
            kwargs.update(event_scope=self.event_scope, allow_legacy=self.is_admin)
        return kwargs

    def get_context_data(self, **kwargs):
        title = f"Modifier · {self.object}" if self.object else self.entity["create_label"]
        return super().get_context_data(page_title=title, **kwargs)

    def get_success_url(self):
        return self.entity_url("detail", pk=self.object.pk)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                if self.model is Resource:
                    check_resource_stock(form.instance)
                elif self.model is ResourceAllocation:
                    check_allocation_stock(form.instance)
                    if form.instance.pk:
                        self.lock_allocation_scope(form.instance.pk)
                    if form.instance.program_event_id is not None:
                        self.require_event(form.instance.program_event_id, lock=True)
                response = super().form_valid(form)
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)

        messages.success(self.request, f"« {self.object} » a été enregistré.")
        return response


class EntityCreateView(EntitySaveMixin, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        if self.model is ResourceAllocation:
            self.check_event_parameter(self.request.GET.get("event_id"))
            for field in ("event_id", "resource", "quantity", "start_time", "end_time"):
                if field in self.request.GET:
                    initial[field] = self.request.GET[field]
        return initial


class EntityUpdateView(EntitySaveMixin, UpdateView):
    pass


class EntityDeleteView(EntityViewMixin, DeleteView):
    template_name = "resources_operations/entity_confirm_delete.html"
    http_method_names = ["get", "head", "post", "options"]

    def get_context_data(self, **kwargs):
        return super().get_context_data(page_title="Confirmer la suppression", **kwargs)

    def get_success_url(self):
        return self.entity_url("list")

    def form_valid(self, form):
        name = str(self.object)
        try:
            with transaction.atomic():
                if self.model is Resource and inventory_for_update(self.object.pk) is None:
                    raise Http404("Cette ressource a déjà été supprimée.")
                if self.model is ResourceAllocation:
                    inventory_for_update(self.object.resource_id)
                    self.object = self.lock_allocation_scope(self.object.pk)
                response = super().form_valid(form)
        except ProtectedError:
            form.add_error(None, "Supprimez ou réaffectez les éléments associés avant de supprimer cette fiche.")
            return self.form_invalid(form)
        messages.success(self.request, f"« {name} » a été supprimé.")
        return response
