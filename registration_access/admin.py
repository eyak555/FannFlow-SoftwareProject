from django.contrib import admin
from .models import AccessPoint, Attendance, Registration, Ticket


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "event_id", "status", "payment_status", "registration_date")
    list_filter = ("status", "payment_status")
<<<<<<< Updated upstream
    search_fields = ("user__first_name", "user__last_name", "user__email", "ticket_type")
=======
    search_fields = ("user__email", "user__last_name", "ticket_type")
>>>>>>> Stashed changes


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "registration", "code", "category", "price", "status")
    list_filter = ("category", "status")
<<<<<<< Updated upstream
    search_fields = (
        "code",
        "registration__user__first_name",
        "registration__user__last_name",
        "registration__user__email",
    )
=======
    search_fields = ("code", "registration__user__email")
>>>>>>> Stashed changes


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "access_point", "check_in", "check_out")
    list_filter = ("access_point",)
    search_fields = ("access_point__name", "ticket__code")


@admin.register(AccessPoint)
class AccessPointAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "event_id", "location", "capacity")
    list_filter = ("event_id",)
    search_fields = ("name", "location")
