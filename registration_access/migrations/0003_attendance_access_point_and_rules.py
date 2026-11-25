import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def link_existing_attendances(apps, schema_editor):
    database = schema_editor.connection.alias
    Attendance = apps.get_model("registration_access", "Attendance")
    AccessPoint = apps.get_model("registration_access", "AccessPoint")

    grouped = {}
    for attendance in Attendance.objects.using(database).select_related(
        "ticket__registration"
    ).order_by("pk"):
        event_id = attendance.ticket.registration.event_id
        name = (attendance.gate or "").strip() or f"Accès historique {attendance.pk}"
        key = (event_id, name[:100])
        entry = grouped.setdefault(key, {"attendances": [], "occupancy": 0})
        entry["attendances"].append(attendance)
        if attendance.check_in and not attendance.check_out:
            entry["occupancy"] += 1

    for (event_id, name), entry in grouped.items():
        capacity = max(entry["occupancy"], 1)
        access_point, _ = AccessPoint.objects.using(database).get_or_create(
            event_id=event_id,
            name=name,
            defaults={
                "location": "À préciser",
                "capacity": capacity,
            },
        )
        if access_point.capacity < capacity:
            access_point.capacity = capacity
            access_point.save(using=database, update_fields=["capacity"])
        for attendance in entry["attendances"]:
            attendance.access_point_id = access_point.pk
            attendance.save(using=database, update_fields=["access_point"])

    used_ticket_ids = Attendance.objects.using(database).filter(
        check_in__isnull=False
    ).values_list("ticket_id", flat=True)
    apps.get_model("registration_access", "Ticket").objects.using(database).filter(
        pk__in=used_ticket_ids
    ).update(status="used")


def restore_legacy_gate_names(apps, schema_editor):
    database = schema_editor.connection.alias
    Attendance = apps.get_model("registration_access", "Attendance")
    for attendance in Attendance.objects.using(database).select_related("access_point"):
        attendance.gate = attendance.access_point.name
        attendance.save(using=database, update_fields=["gate"])


class Migration(migrations.Migration):

    dependencies = [
        ("registration_access", "0002_alter_ticket_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendance",
            name="access_point",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attendances",
                to="registration_access.accesspoint",
                verbose_name="Point d’accès",
            ),
        ),
        migrations.RunPython(
            link_existing_attendances,
            restore_legacy_gate_names,
        ),
        migrations.AlterField(
            model_name="attendance",
            name="access_point",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attendances",
                to="registration_access.accesspoint",
                verbose_name="Point d’accès",
            ),
        ),
        migrations.RemoveField(
            model_name="attendance",
            name="gate",
        ),
        migrations.AlterField(
            model_name="attendance",
            name="ticket",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="attendances",
                to="registration_access.ticket",
                verbose_name="Billet",
            ),
        ),
        migrations.AlterField(
            model_name="ticket",
            name="price",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Prix",
            ),
        ),
        migrations.AlterField(
            model_name="accesspoint",
            name="capacity",
            field=models.PositiveIntegerField(
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Capacité maximale simultanée",
            ),
        ),
        migrations.AlterField(
            model_name="registration",
            name="event_id",
            field=models.PositiveIntegerField(
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Événement",
            ),
        ),
        migrations.AlterField(
            model_name="accesspoint",
            name="event_id",
            field=models.PositiveIntegerField(
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Événement",
            ),
        ),
    ]
