from collections import defaultdict
from itertools import accumulate

from django.core.exceptions import ValidationError
from django.db.models import F
from django.utils import timezone

from .models import Resource, ResourceAllocation


def peak_quantity(allocations, start, end=None):
    """Calcule le plus grand nombre d’unités réservées au même instant."""
    allocations = allocations.filter(end_time__gt=start)
    if end is not None:
        allocations = allocations.filter(start_time__lt=end)

    deltas = defaultdict(int)
    for allocation_start, allocation_end, quantity in allocations.values_list(
        "start_time", "end_time", "quantity"
    ).order_by():
        deltas[max(start, allocation_start)] += quantity
        deltas[min(end, allocation_end) if end is not None else allocation_end] -= quantity

    return max(accumulate(deltas[instant] for instant in sorted(deltas)), default=0)


def inventory_for_update(resource_id):
    # L’écriture verrouille aussi l’inventaire sur SQLite. Elle doit précéder
    # les lectures dans la transaction d’enregistrement.
    resources = Resource.objects.filter(pk=resource_id)
    if not resources.update(quantity=F("quantity")):
        return None
    return resources.values_list("quantity", flat=True).get()


def check_resource_stock(resource):
    if resource._state.adding:
        return
    previous_quantity = inventory_for_update(resource.pk)
    if previous_quantity is None:
        raise ValidationError("Cette ressource a été supprimée. Revenez à la liste.")
    if resource.quantity < previous_quantity:
        reserved = peak_quantity(resource.allocations.all(), timezone.now())
        if resource.quantity < reserved:
            raise ValidationError({
                "quantity": f"Les allocations en cours ou à venir nécessitent au moins {reserved} unité(s).",
            })


def check_allocation_stock(allocation):
    stock = inventory_for_update(allocation.resource_id)
    if stock is None:
        raise ValidationError({"resource": "Cette ressource n’est plus disponible."})

    allocation_rows = ResourceAllocation.objects
    if not allocation._state.adding and not allocation_rows.select_for_update().filter(pk=allocation.pk).exists():
        raise ValidationError("Cette allocation a été supprimée. Revenez à la liste.")

    start = max(allocation.start_time, timezone.now())
    if allocation.end_time <= start:
        return

    other_allocations = allocation_rows.filter(resource_id=allocation.resource_id).exclude(pk=allocation.pk)
    reserved = peak_quantity(other_allocations, start, allocation.end_time)
    available = stock - reserved
    if allocation.quantity > available:
        raise ValidationError({
            "quantity": f"Il reste {max(0, available)} unité(s) disponible(s) sur toute la période demandée.",
        })
