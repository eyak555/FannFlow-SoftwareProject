from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import OperationalError, models, transaction
from django.urls import reverse
from django.utils.html import format_html

from .forms import ResourceAllocationForm, ResourceForm, VenueForm
from .inventory import check_allocation_stock, check_resource_stock
from .models import Resource, ResourceAllocation, Venue
from .permissions import can_administer_operations, is_operations_director


class AdminInventoryFormMixin:
    def _post_clean(self):
        super()._post_clean()
        if self.errors:
            return

        # L’admin garde la validation et l’enregistrement dans la même transaction.
        try:
            with transaction.atomic():
                self.validate_stock(self.instance)
        except ValidationError as error:
            self.add_error(None, error)
        except OperationalError as error:
            sqlite_code = getattr(error.__cause__, "sqlite_errorcode", 0)
            if (sqlite_code & 0xFF) not in (5, 6):
                raise
            self.add_error(None, "L’inventaire est en cours de modification. Réessayez d’enregistrer.")


class ResourceAdminForm(AdminInventoryFormMixin, ResourceForm):
    validate_stock = staticmethod(check_resource_stock)


class ResourceAllocationAdminForm(AdminInventoryFormMixin, ResourceAllocationForm):
    validate_stock = staticmethod(check_allocation_stock)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event_id"].help_text = format_html(
            '<a href="{}">Gérer les fiches événementielles</a>',
            reverse("resources_operations:event_requirements"),
        )


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    form = VenueForm
    list_display = ("name", "type", "address", "capacity", "parking_capacity", "accessibility")
    list_filter = ("type", "accessibility")
    search_fields = ("name", "type", "address")
    readonly_fields = ("map_link", "compatibility_link")

    @admin.display(description="Carte")
    def map_link(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return None
        return format_html(
            '<a href="https://www.openstreetmap.org/?mlat={lat}&amp;mlon={lon}#map=17/{lat}/{lon}">'
            'Ouvrir dans OpenStreetMap</a>',
            lat=obj.latitude,
            lon=obj.longitude,
        )

    @admin.display(description="Adéquation avec un événement")
    def compatibility_link(self, obj):
        if obj.pk is None:
            return None
        return format_html(
            '<a href="{}#venue-compatibility">Comparer les besoins</a>',
            reverse("resources_operations:entity_detail", args=["venues", obj.pk]),
        )


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    form = ResourceAdminForm
    change_list_template = "admin/resources_operations/resource/change_list.html"
    list_display = ("name", "type", "status", "quantity", "low_stock_threshold", "unit_cost", "location")
    list_filter = ("status", "type")
    search_fields = ("name", "type", "location")

    def inventory_role_allowed(self, request):
        user = request.user
        return not is_operations_director(user) or can_administer_operations(user)

    def has_view_permission(self, request, obj=None):
        return self.inventory_role_allowed(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self.inventory_role_allowed(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.inventory_role_allowed(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.inventory_role_allowed(request) and super().has_delete_permission(request, obj)


@admin.register(ResourceAllocation)
class ResourceAllocationAdmin(admin.ModelAdmin):
    form = ResourceAllocationAdminForm
    formfield_overrides = {models.DateTimeField: {"form_class": forms.DateTimeField}}
    list_display = ("resource", "event_id", "quantity", "used_quantity", "start_time", "end_time")
    list_filter = ("start_time", "end_time")
    list_select_related = ("resource",)
    search_fields = ("resource__name", "=event_id")
