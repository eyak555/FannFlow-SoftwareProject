from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .entities import MODULE
from .forms import ResourceAllocationForm, ResourceForm, VenueForm
from .inventory import check_allocation_stock, check_resource_stock, inventory_for_update
from .models import Resource, ResourceAllocation, Venue


ENTITIES = {entity["slug"]: entity for entity in MODULE["entities"]}
FORMS = {
    "venues": VenueForm,
    "resources": ResourceForm,
    "resource-allocations": ResourceAllocationForm,
}


class OperationsAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    permission_denied_message = "Votre rôle ne donne pas accès à cette section."

    def get_login_url(self):
        if get_user_model()._meta.label_lower == "users_teams.user":
            return settings.LOGIN_URL
        return reverse("resources_operations:login")

    @cached_property
    def is_admin(self):
        user = self.request.user
        return (
            user.is_superuser
            or getattr(user, "is_administrator", False)
            or user.groups.filter(name="Administrateur").exists()
        )

    @cached_property
    def is_director(self):
        user = self.request.user
        return (
            getattr(user, "business_role", "") == "directeur"
            or user.groups.filter(name="Directeur").exists()
        )

    def test_func(self):
        return self.is_admin or (self.kwargs.get("entity") != "resources" and self.is_director)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["module"] = MODULE
        context["sections"] = [
            entity for entity in MODULE["entities"] if self.is_admin or entity["slug"] != "resources"
        ]
        context["show_local_logout"] = get_user_model()._meta.label_lower != "users_teams.user"
        return context


class ModuleHomeView(OperationsAccessMixin, TemplateView):
    template_name = "resources_operations/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = MODULE["title"]
        context["overview"] = [
            {"entity": entity, "count": FORMS[entity["slug"]]._meta.model.objects.count()}
            for entity in context["sections"]
        ]
        return context


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
            return queryset.select_related("resource")
        return queryset

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
        else:
            if self.search:
                criteria = Q(resource__name__icontains=self.search)
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
        return super().get_context_data(page_title=str(self.object), **kwargs)


class EntitySaveMixin(EntityViewMixin):
    template_name = "resources_operations/entity_form.html"

    def get_form_class(self):
        return FORMS[self.entity["slug"]]

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
                response = super().form_valid(form)
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)

        messages.success(self.request, f"« {self.object} » a été enregistré.")
        return response


class EntityCreateView(EntitySaveMixin, CreateView):
    pass


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
                response = super().form_valid(form)
        except ProtectedError:
            form.add_error(None, "Supprimez ou réaffectez les éléments associés avant de supprimer cette fiche.")
            return self.form_invalid(form)
        messages.success(self.request, f"« {name} » a été supprimé.")
        return response
