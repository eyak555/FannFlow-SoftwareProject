import uuid

from django.db import migrations, models


def normalize_registration_ticket_types(apps, schema_editor):
    database = schema_editor.connection.alias
    Registration = apps.get_model("registration_access", "Registration")
    values = {
        "standard": "standard",
        "standard ticket": "standard",
        "vip": "vip",
        "group": "group",
        "groupe": "group",
    }
    registrations = list(
        Registration.objects.using(database).values_list("pk", "ticket_type")
    )
    for registration_id, ticket_type in registrations:
        normalized = values.get(ticket_type.strip().casefold(), "standard")
        if ticket_type != normalized:
            Registration.objects.using(database).filter(pk=registration_id).update(
                ticket_type=normalized
            )


def restore_registration_ticket_type_labels(apps, schema_editor):
    database = schema_editor.connection.alias
    Registration = apps.get_model("registration_access", "Registration")
    labels = {"standard": "Standard", "vip": "VIP", "group": "Groupe"}
    registrations = list(
        Registration.objects.using(database).values_list("pk", "ticket_type")
    )
    for registration_id, ticket_type in registrations:
        label = labels.get(ticket_type, "Standard")
        Registration.objects.using(database).filter(pk=registration_id).update(
            ticket_type=label
        )


def regenerate_ticket_codes(apps, schema_editor):
    database = schema_editor.connection.alias
    Ticket = apps.get_model("registration_access", "Ticket")
    tickets = Ticket.objects.using(database).only("pk", "code").order_by("pk")
    ticket_ids = list(tickets.values_list("pk", flat=True))
    for ticket_id in ticket_ids:
        temporary_code = f"TMP-{ticket_id}-{uuid.uuid4().hex}"
        Ticket.objects.using(database).filter(pk=ticket_id).update(
            code=temporary_code
        )
    for ticket_id in ticket_ids:
        Ticket.objects.using(database).filter(pk=ticket_id).update(
            code=f"FF-{ticket_id:06d}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('registration_access', '0003_attendance_access_point_and_rules'),
    ]

    operations = [
        migrations.RunPython(
            normalize_registration_ticket_types,
            restore_registration_ticket_type_labels,
        ),
        migrations.RenameField(
            model_name="ticket",
            old_name="qr_code",
            new_name="code",
        ),
        migrations.RunPython(
            regenerate_ticket_codes,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="ticket",
            name="code",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=32,
                unique=True,
                verbose_name="Code billet",
            ),
        ),
        migrations.AlterField(
            model_name="registration",
            name="ticket_type",
            field=models.CharField(
                choices=[
                    ("standard", "Standard"),
                    ("vip", "VIP"),
                    ("group", "Groupe"),
                ],
                max_length=20,
                verbose_name="Type de billet",
            ),
        ),
    ]
