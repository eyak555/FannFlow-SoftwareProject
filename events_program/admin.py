from django.contrib import admin

from .models import Activity, ActivitySpeaker, Event, Speaker


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "start_date", "status", "director")
    list_filter = ("status", "event_type", "category")
    search_fields = ("title", "description", "location")
    date_hierarchy = "start_date"


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "event", "activity_type", "start_time", "end_time")
    list_filter = ("activity_type", "event")
    search_fields = ("title", "event__title")


@admin.register(Speaker)
class SpeakerAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "country", "expertise")
    search_fields = ("name", "organization", "expertise")


@admin.register(ActivitySpeaker)
class ActivitySpeakerAdmin(admin.ModelAdmin):
    list_display = ("activity", "speaker")
    list_filter = ("activity__event",)
