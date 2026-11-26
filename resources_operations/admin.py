from django.contrib import admin

from .models import Venue


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "venue_type", "capacity")
    list_filter = ("venue_type", "city")
    search_fields = ("name", "address", "city")
