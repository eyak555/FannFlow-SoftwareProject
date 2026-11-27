from django.contrib import admin

from .models import Budget, Expense, Partnership, Sponsor, SponsorshipPackage


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = ("company_name", "industry", "email", "phone")
    search_fields = ("company_name", "industry", "email", "phone")
    list_filter = ("industry",)


@admin.register(SponsorshipPackage)
class SponsorshipPackageAdmin(admin.ModelAdmin):
    list_display = ("package_name", "price")
    search_fields = ("package_name", "description")
    list_filter = ("package_name",)


@admin.register(Partnership)
class PartnershipAdmin(admin.ModelAdmin):
    list_display = ("sponsor", "event", "package", "amount", "start_date", "end_date", "status")
    search_fields = ("sponsor__company_name", "event__title", "package__package_name")
    list_filter = ("status", "package", "start_date")
    date_hierarchy = "start_date"


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("event", "planned_amount", "created_at", "updated_at")
    search_fields = ("event__title",)
    list_filter = ("created_at",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("event", "category", "amount", "date")
    search_fields = ("event__title", "description")
    list_filter = ("category", "date")
    date_hierarchy = "date"
