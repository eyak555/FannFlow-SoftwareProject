from events_program.models import Event

from .models import Resource, ResourceAllocation, Venue


OPERATIONS_ADMIN_PERMISSIONS = tuple(
    f"resources_operations.{action}_{model._meta.model_name}"
    for model in (Venue, Resource, ResourceAllocation)
    for action in ("view", "add", "change", "delete")
)


def can_administer_operations(user):
    return user.is_authenticated and user.is_active and (
        user.is_superuser
        or getattr(user, "is_administrator", False)
        or user.groups.filter(name__in=("Administrateur", "Admin")).exists()
        or user.has_perms(OPERATIONS_ADMIN_PERMISSIONS)
    )


def is_operations_director(user):
    return user.is_authenticated and user.is_active and (
        getattr(user, "business_role", "") == "directeur"
        or user.groups.filter(name__in=("Directeur", "Director")).exists()
    )


def events_for(user):
    if can_administer_operations(user):
        return Event.objects.all()
    if is_operations_director(user):
        return Event.objects.filter(director_id=user.pk)
    return Event.objects.none()
