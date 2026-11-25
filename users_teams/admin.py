from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Administration Django technique. Le hash et l'encodage facial ne sont pas exposés."""

    list_display = ("email", "last_name", "first_name", "role", "business_role", "status", "created_at")
    list_filter = ("role", "business_role", "status")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("last_name", "first_name")
    exclude = ("password", "face_encoding", "groups", "user_permissions")
    readonly_fields = ("created_at", "last_login")
