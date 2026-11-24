import secrets
from decimal import Decimal

from .models import Registration, Ticket


def ticket_category_for_registration(registration):
    ticket_type = registration.ticket_type.strip().casefold()
    for value, label in Ticket.CATEGORY_CHOICES:
        if ticket_type in (value.casefold(), label.casefold()):
            return value
    return Ticket.CATEGORY_STANDARD


def ticket_status_for_registration(registration, ticket):
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
    )


def create_registration_ticket(registration):
    ticket = Ticket.objects.create(
        registration=registration,
        qr_code=secrets.token_urlsafe(32),
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
        if status != ticket.status:
            ticket.status = status
            ticket.save(update_fields=["status"])
