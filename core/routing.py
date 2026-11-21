"""Chemins CRUD génériques, identiques d'un module à l'autre.

Une branche métier ajoute ses vues réelles *avant* ces chemins dans
l'``urls.py`` de son application, sans toucher au socle.
"""

from django.urls import path


def crud_patterns(views):
    return [
        path("", views.module_home, name="home"),
        path(
            "<slug:entity>/nouveau/",
            views.crud_placeholder,
            {"action": "create"},
            name="entity_create",
        ),
        path(
            "<slug:entity>/<int:pk>/modifier/",
            views.crud_placeholder,
            {"action": "update"},
            name="entity_update",
        ),
        path(
            "<slug:entity>/<int:pk>/supprimer/",
            views.crud_placeholder,
            {"action": "delete"},
            name="entity_delete",
        ),
        path(
            "<slug:entity>/<int:pk>/",
            views.crud_placeholder,
            {"action": "detail"},
            name="entity_detail",
        ),
        path(
            "<slug:entity>/",
            views.crud_placeholder,
            {"action": "list"},
            name="entity_list",
        ),
    ]
