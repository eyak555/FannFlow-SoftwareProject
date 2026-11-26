from django.urls import reverse

from core.access import BackOfficeAccessMiddleware as CoreBackOfficeAccessMiddleware
from core.context_processors import navigation as core_navigation

from .entities import get_accessible_sections


class BackOfficeAccessMiddleware(CoreBackOfficeAccessMiddleware):
    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if match and match.namespace == "resources_operations" and get_accessible_sections(request.user):
            return None
        return super().process_view(request, view_func, view_args, view_kwargs)


def navigation(request):
    context = core_navigation(request)
    sections = get_accessible_sections(request.user)
    modules = []
    for module in context["fannflow_modules"]:
        if module["app_name"] != "resources_operations":
            modules.append(module)
        elif sections:
            modules.append({
                **module, "entities": sections,
                "href": reverse("resources_operations:home"), "locked": False,
            })
    context["fannflow_modules"] = modules
    return context
