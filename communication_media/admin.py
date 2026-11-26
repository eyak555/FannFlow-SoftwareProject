from django.contrib import admin

from .models import MediaContact


@admin.register(MediaContact)
class MediaContactAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "role", "email", "phone")
    list_filter = ("role",)
    search_fields = ("name", "organization", "email")
