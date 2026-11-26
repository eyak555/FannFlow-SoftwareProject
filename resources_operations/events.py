from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class PlanningEvent:
    id: int
    name: str
    attendees: int | None = None
    minimum_surface: Decimal | None = None
    parking_spaces: int = 0
    needs_accessibility: bool = False
    venue_name: str | None = None

    @property
    def label(self):
        return f"{self.name} (#{self.id})"


def planning_events(event_scope):
    events = event_scope.order_by("title", "pk").values_list(
        "pk", "title", "capacity", "operations_requirements__attendees",
        "operations_requirements__minimum_surface", "operations_requirements__parking_spaces",
        "operations_requirements__needs_accessibility", "operations_requirements__venue__name",
    )
    return {
        event_id: PlanningEvent(event_id, title, attendees or capacity, surface, parking or 0, bool(pmr), venue)
        for event_id, title, capacity, attendees, surface, parking, pmr, venue in events
    }


def event_choices(event_scope):
    events = event_scope.order_by("title", "pk").values_list("pk", "title")
    return [("", "Sélectionner un événement"), *((pk, f"{title} (#{pk})") for pk, title in events)]


def venue_criteria(venue, event):
    def criterion(label, required, available):
        if required is None or available is None:
            status = "unknown"
        else:
            status = "pass" if available >= required else "fail"
        return {"label": label, "required": required, "available": available, "status": status}

    criteria = [criterion("Participants", event.attendees, venue.capacity)]
    if event.minimum_surface is not None:
        criteria.append(criterion("Surface (m²)", event.minimum_surface, venue.surface))
    if event.parking_spaces:
        criteria.append(criterion("Places de parking", event.parking_spaces, venue.parking_capacity))
    if event.needs_accessibility:
        criteria.append({
            "label": "Accessibilité PMR",
            "required": "Oui",
            "available": "Oui" if venue.accessibility else "Non",
            "status": "pass" if venue.accessibility else "fail",
        })
    return criteria
