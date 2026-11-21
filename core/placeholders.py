"""Pages d'attente des opérations CRUD.

Elles montrent le gabarit (liste, formulaire, détail, confirmation)
et refusent toute écriture. La logique métier se code dans la branche
du module.
"""

from django.contrib import messages
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect, render

ACTIONS = {
    "list": "Liste",
    "create": "Création",
    "detail": "Détail",
    "update": "Modification",
    "delete": "Suppression",
}

TEMPLATES = {
    "list": "core/layouts/list.html",
    "create": "core/layouts/form.html",
    "update": "core/layouts/form.html",
    "detail": "core/layouts/detail.html",
    "delete": "core/layouts/confirm_delete.html",
}

NOT_IMPLEMENTED = (
    "Cette opération n’est pas implémentée dans le socle commun. "
    "Elle se développe dans la branche Git du module."
)


def render_module_home(request, module):
    return render(
        request,
        "core/layouts/module_home.html",
        {
            "module": module,
            "page_title": module["title"],
            "page_intro": module["summary"],
        },
    )


def render_crud_placeholder(request, module, entity_slug, action, pk=None):
    entity = next(
        (item for item in module["entities"] if item["slug"] == entity_slug),
        None,
    )
    if entity is None or action not in ACTIONS:
        raise Http404("Cette page n’existe pas dans le module.")

    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "HEAD", "POST"])

    if request.method == "POST":
        messages.error(request, NOT_IMPLEMENTED)
        return redirect(request.path)

    return render(
        request,
        TEMPLATES[action],
        {
            "module": module,
            "entity": entity,
            "action": action,
            "action_label": ACTIONS[action],
            "pk": pk,
            "placeholder": True,
            "page_title": f"{ACTIONS[action]} — {entity['name']}",
            "page_intro": "",
        },
    )
