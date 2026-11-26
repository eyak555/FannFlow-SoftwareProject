from collections import defaultdict
from datetime import datetime, time, timedelta
from math import ceil
from statistics import linear_regression, mean

from django.db.models import Q
from django.utils import timezone

from .inventory import reservation_peak
from .models import Resource, ResourceAllocation


WEEK = timedelta(days=7)
HISTORY_WEEKS = 12
FORECAST_WEEKS = 4


def week_start(moment):
    local_day = timezone.localdate(moment)
    monday = local_day - timedelta(days=local_day.weekday())
    return datetime.combine(monday, time.min, tzinfo=timezone.get_current_timezone())


def trend_prediction(samples):
    slope, intercept = linear_regression(range(len(samples)), samples)
    return max(0, slope * len(samples) + intercept)


def average_prediction(samples):
    return mean(samples[-4:])


def demand_forecast(history):
    """Sélectionne le modèle selon l’erreur de prévision hors échantillon."""
    if len(history) < 6 or sum(value > 0 for value in history) < 3:
        return None

    models = {
        "Régression linéaire": trend_prediction,
        "Moyenne mobile": average_prediction,
    }
    validation_weeks = range(max(4, len(history) - 4), len(history))
    errors = {
        name: mean(abs(predict(history[:index]) - history[index]) for index in validation_weeks)
        for name, predict in models.items()
    }
    method = min(errors, key=errors.get)
    samples = list(history)
    for _ in range(FORECAST_WEEKS):
        samples.append(models[method](samples))
    return {
        "method": method,
        "error": errors[method],
        "peaks": [ceil(value) for value in samples[-FORECAST_WEEKS:]],
    }


def inventory_report(now):
    current_week = week_start(now)
    earliest = current_week - HISTORY_WEEKS * WEEK
    horizon = current_week + FORECAST_WEEKS * WEEK
    allocations = ResourceAllocation.objects.filter(
        Q(end_time__gt=earliest, start_time__lt=horizon) | Q(used_quantity__isnull=False),
    ).order_by().values_list("resource_id", "start_time", "end_time", "quantity", "used_quantity")
    by_resource = defaultdict(list)
    for resource_id, start, end, planned, used in allocations:
        by_resource[resource_id].append((start, end, planned, used))

    rows = []
    for resource in Resource.objects.all():
        rows.append(resource_report(resource, by_resource[resource.pk], now, current_week, earliest))
    return rows


def resource_report(resource, allocations, now, current_week, earliest):
    past = [(start, end, planned if used is None else used) for start, end, planned, used in allocations
            if start < current_week]
    history = []
    if past:
        first_week = max(earliest, week_start(min(start for start, _, _ in past)))
        weeks = (current_week.date() - first_week.date()).days // 7
        for index in range(weeks):
            start = first_week + index * WEEK
            history.append(reservation_peak(past, start, start + WEEK))
    model = demand_forecast(history)

    planned_slots = [(start, end, planned) for start, end, planned, _ in allocations if end > now]
    currently_reserved = sum(planned for start, _, planned in planned_slots if start <= now)
    stock = resource.bookable_quantity
    free = max(0, stock - currently_reserved)
    periods = []
    for index in range(FORECAST_WEEKS):
        start = current_week + index * WEEK
        planned = reservation_peak(planned_slots, max(now, start), start + WEEK)
        estimate = model["peaks"][index] if model else None
        shortage = max(planned, estimate or 0) - stock
        periods.append({
            "start": start, "end": start + timedelta(days=6), "reserved": planned,
            "estimated": estimate, "shortage": max(0, shortage),
        })

    return {
        "resource": resource, "free": free, "low": free <= resource.low_stock_threshold,
        "used": sum(used or 0 for _, _, _, used in allocations),
        "periods": periods, "shortage": max(period["shortage"] for period in periods),
        "model": model,
    }
