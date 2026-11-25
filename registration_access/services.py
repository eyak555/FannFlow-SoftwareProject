from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AccessPoint, Attendance, Registration, Ticket


def ticket_category_for_registration(registration):
    ticket_type = registration.ticket_type.strip().casefold()
    for value, label in Ticket.CATEGORY_CHOICES:
        if ticket_type in (value.casefold(), label.casefold()):
            return value
    return Ticket.CATEGORY_STANDARD


def ticket_status_for_registration(registration, ticket):
    if ticket.status == Ticket.STATUS_USED:
        return Ticket.STATUS_USED
    if registration.status == Registration.STATUS_CANCELLED:
        return Ticket.STATUS_CANCELLED
    if registration.payment_status == Registration.PAYMENT_REFUNDED:
        return Ticket.STATUS_REFUND
    if registration.status == Registration.STATUS_CONFIRMED and (
        ticket.price == Decimal("0.00")
        or registration.payment_status == Registration.PAYMENT_PAID
    ):
        return Ticket.STATUS_AVAILABLE
    if ticket.status in (Ticket.STATUS_AVAILABLE, Ticket.STATUS_PENDING):
        return Ticket.STATUS_PENDING
    return ticket.status


def ticket_is_ready_for_qr(ticket):
    registration = ticket.registration
    return (
        ticket.status == Ticket.STATUS_AVAILABLE
        and registration.status == Registration.STATUS_CONFIRMED
        and (
            ticket.price == Decimal("0.00")
            or registration.payment_status == Registration.PAYMENT_PAID
        )
        and registration.payment_status != Registration.PAYMENT_REFUNDED
    )


def create_registration_ticket(registration):
    ticket = Ticket.objects.create(
        registration=registration,
        price=Decimal("0.00"),
        category=ticket_category_for_registration(registration),
        status=Ticket.STATUS_PENDING,
    )
    ticket.status = ticket_status_for_registration(registration, ticket)
    if ticket.status != Ticket.STATUS_PENDING:
        ticket.save(update_fields=["status"])
    return ticket


def sync_registration_tickets(registration):
    for ticket in registration.tickets.all():
        status = ticket_status_for_registration(registration, ticket)
        category = ticket.category
        if ticket.status != Ticket.STATUS_USED:
            category = ticket_category_for_registration(registration)
        changed_fields = []
        if status != ticket.status:
            ticket.status = status
            changed_fields.append("status")
        if category != ticket.category:
            ticket.category = category
            changed_fields.append("category")
        if changed_fields:
            ticket.save(update_fields=changed_fields)


@transaction.atomic
def check_in_ticket(code, access_point):
    try:
        locked_access_point = AccessPoint.objects.select_for_update().get(
            pk=access_point.pk
        )
    except AccessPoint.DoesNotExist as exc:
        raise ValidationError("Le point d’accès sélectionné n’existe plus.") from exc

    try:
        ticket = Ticket.objects.select_for_update().select_related(
            "registration"
        ).get(code=code.strip().upper())
    except Ticket.DoesNotExist as exc:
        raise ValidationError({"code": "Aucun billet ne correspond à ce code."}) from exc

    if ticket.registration.event_id != locked_access_point.event_id:
        raise ValidationError({
            "access_point": "Ce billet concerne un autre événement que le point d’accès."
        })
    if not ticket_is_ready_for_qr(ticket):
        raise ValidationError(
            "Ce billet n’est pas valide : l’inscription doit être confirmée et le paiement effectué."
        )
    if Attendance.objects.filter(ticket=ticket, check_in__isnull=False).exists():
        raise ValidationError("Ce billet a déjà été utilisé ; la réentrée n’est pas autorisée.")

    occupancy = Attendance.objects.filter(
        access_point=locked_access_point,
        check_in__isnull=False,
        check_out__isnull=True,
    ).count()
    if occupancy >= locked_access_point.capacity:
        raise ValidationError(
            "La capacité maximale de ce point d’accès est atteinte."
        )

    attendance = Attendance(
        ticket=ticket,
        access_point=locked_access_point,
        check_in=timezone.now(),
    )
    try:
        attendance.full_clean()
    except ValidationError as error:
        raise ValidationError(error.messages) from error
    attendance.save()

    ticket.status = Ticket.STATUS_USED
    ticket.save(update_fields=["status"])
    return attendance


@transaction.atomic
def check_out_attendance(attendance_id):
    try:
        attendance = Attendance.objects.select_for_update().select_related(
            "access_point"
        ).get(pk=attendance_id)
    except Attendance.DoesNotExist as exc:
        raise ValidationError("Cette présence n’existe plus.") from exc

    AccessPoint.objects.select_for_update().get(pk=attendance.access_point_id)
    if not attendance.check_in:
        raise ValidationError("Aucune entrée n’est enregistrée pour cette présence.")
    if attendance.check_out:
        raise ValidationError("La sortie de ce participant est déjà enregistrée.")

    attendance.check_out = timezone.now()
    attendance.full_clean()
    attendance.save(update_fields=["check_out"])
    return attendance


@transaction.atomic
def save_attendance(attendance):
    locked_access_point = AccessPoint.objects.select_for_update().get(
        pk=attendance.access_point_id
    )
    ticket = Ticket.objects.select_for_update().select_related(
        "registration"
    ).get(pk=attendance.ticket_id)
    attendance.access_point = locked_access_point
    attendance.ticket = ticket
    attendance.full_clean()
    attendance.save()

    if attendance.check_in and ticket.status != Ticket.STATUS_USED:
        ticket.status = Ticket.STATUS_USED
        ticket.save(update_fields=["status"])
    return attendance
