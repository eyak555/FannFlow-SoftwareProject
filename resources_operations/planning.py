from collections import defaultdict

from .inventory import reservation_peak
from .models import Resource, ResourceAllocation


def allocation_options(resource_type, quantity, start_time, end_time, latest_start=None):
    """Cherche pour chaque ressource le premier créneau qui couvre toute la durée."""
    duration = end_time - start_time
    latest_start = latest_start or start_time
    resources = list(Resource.objects.filter(
        type=resource_type, status=Resource.Status.AVAILABLE, quantity__gte=quantity,
    ))
    reservations = defaultdict(list)
    slots = ResourceAllocation.objects.filter(
        resource__in=resources, end_time__gt=start_time, start_time__lt=latest_start + duration,
    ).order_by().values_list("resource_id", "start_time", "end_time", "quantity")
    for resource_id, start, end, reserved in slots:
        reservations[resource_id].append((start, end, reserved))

    options = []
    for resource in resources:
        slots = reservations[resource.pk]
        # La disponibilité ne s’améliore qu’à la libération d’une réservation.
        candidate_starts = {start_time, *(end for _, end, _ in slots if end <= latest_start)}
        for start in sorted(candidate_starts):
            end = start + duration
            available = resource.bookable_quantity - reservation_peak(slots, start, end)
            if available >= quantity:
                options.append({
                    "resource": resource, "start": start, "end": end,
                    "available": available, "cost": resource.unit_cost * quantity,
                })
                break
    return sorted(options, key=lambda row: (row["cost"], row["start"], -row["available"], row["resource"].pk))
