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

    return reservation_peak(allocations.order_by().values_list("start_time", "end_time", "quantity"), start, end)


def reservation_peak(reservations, start, end=None):
    deltas = defaultdict(int)
    for allocation_start, allocation_end, quantity in reservations:
        if allocation_end <= start or (end is not None and allocation_start >= end):
            continue
        deltas[max(start, allocation_start)] += quantity
        deltas[min(end, allocation_end) if end is not None else allocation_end] -= quantity

    return max(accumulate(deltas[instant] for instant in sorted(deltas)), default=0)


def inventory_for_update(resource_id):
    # L’écriture verrouille aussi l’inventaire sur SQLite. Elle doit précéder
    # les lectures dans la transaction d’enregistrement.
    resources = Resource.objects.filter(pk=resource_id)
    if not resources.update(quantity=F("quantity")):
        return None
    return resources.get()


def check_resource_stock(resource):
    if resource._state.adding:
        return
    previous = inventory_for_update(resource.pk)
    if previous is None:
        raise ValidationError("Cette ressource a été supprimée. Revenez à la liste.")
    if resource.bookable_quantity < previous.bookable_quantity:
        reserved = peak_quantity(resource.allocations.all(), timezone.now())
        if resource.bookable_quantity < reserved:
            field = "quantity" if resource.status == Resource.Status.AVAILABLE else "status"
            raise ValidationError({
                field: f"Les allocations en cours ou à venir nécessitent au moins {reserved} unité(s).",
            })


def check_allocation_stock(allocation):
    resource = inventory_for_update(allocation.resource_id)
    if resource is None:
        raise ValidationError({"resource": "Cette ressource n’est plus disponible."})

    allocation_rows = ResourceAllocation.objects
    if not allocation._state.adding and not allocation_rows.select_for_update().filter(pk=allocation.pk).exists():
        raise ValidationError("Cette allocation a été supprimée. Revenez à la liste.")

    start = max(allocation.start_time, timezone.now())
    if allocation.end_time <= start:
        return
    if resource.status != Resource.Status.AVAILABLE:
        raise ValidationError({"resource": "Cette ressource est indisponible pour la période demandée."})

    other_allocations = allocation_rows.filter(resource_id=allocation.resource_id).exclude(pk=allocation.pk)
    reserved = peak_quantity(other_allocations, start, allocation.end_time)
    available = resource.bookable_quantity - reserved
    if allocation.quantity > available:
        raise ValidationError({
            "quantity": f"Il reste {max(0, available)} unité(s) disponible(s) sur toute la période demandée.",
        })
