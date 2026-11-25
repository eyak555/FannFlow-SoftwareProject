from django.contrib import admin

from .models import AccountActivity, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Administration Django technique. Le hash et l'encodage facial ne sont pas exposés."""

    list_display = ("email", "last_name", "first_name", "role", "business_role", "status", "created_at")
    list_filter = ("role", "business_role", "status")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("last_name", "first_name")
    exclude = ("password", "face_encoding", "groups", "user_permissions")
    readonly_fields = ("created_at", "last_login")


@admin.register(AccountActivity)
class AccountActivityAdmin(admin.ModelAdmin):
    """Journal en lecture seule : il ne se modifie pas à la main."""

    list_display = ("created_at", "action", "target_label", "actor", "details")
    list_filter = ("action",)
    search_fields = ("target_label", "details")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
