from django.contrib import admin

from .forms import CommunicationForm, MediaForm, PressKitForm, PublicationForm
from .models import Communication, Media, MediaContact, PressKit, Publication


@admin.register(MediaContact)
class MediaContactAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "role", "email", "phone")
    list_filter = ("role",)
    search_fields = ("name", "organization", "email")


# L'administration réutilise les formulaires du module : mêmes contrôles.


@admin.register(Communication)
class CommunicationAdmin(admin.ModelAdmin):
    form = CommunicationForm
    list_display = ("title", "type", "language", "status", "publication_date")
    list_filter = ("status", "type", "language")
    search_fields = ("title", "content")


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    form = MediaForm
    list_display = ("name", "media_type", "format", "size", "communication", "uploaded_at")
    list_filter = ("media_type",)
    search_fields = ("name", "original_filename")
    readonly_fields = ("original_filename", "format", "size")


@admin.register(PressKit)
class PressKitAdmin(admin.ModelAdmin):
    form = PressKitForm
    list_display = ("title", "created_at")
    search_fields = ("title", "description")


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    form = PublicationForm
    list_display = ("platform", "excerpt", "publication_date", "status")
    list_filter = ("platform", "status")
    search_fields = ("content",)
