from django.contrib import admin
from .models import AccessPoint, Attendance, Registration, Ticket


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "event_id", "status", "payment_status", "registration_date")
    list_filter = ("status", "payment_status")
    search_fields = ("user__username", "user__email", "ticket_type")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "registration", "qr_code", "category", "price", "status")
    list_filter = ("category", "status")
    search_fields = ("qr_code",)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "check_in", "check_out", "gate")
    search_fields = ("gate", "ticket__qr_code")


@admin.register(AccessPoint)
class AccessPointAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "event_id", "location", "capacity")
    list_filter = ("event_id",)
    search_fields = ("name", "location")
