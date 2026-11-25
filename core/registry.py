"""Agrège les modules déjà décrits dans le cahier des charges.

Les données de chaque module vivent dans ``<app>/entities.py``.
Ce registre ne fait que les exposer au gabarit et à la navigation,
avec une icône (Lucide) et une description d'interface.
"""

# Présentation d'interface uniquement : aucune donnée métier.
MODULE_PRESENTATION = {
    "users_teams": {
        "icon": "users",
        "pitch": "Comptes, rôles et équipes d’organisation.",
    },
    "events_program": {
        "icon": "calendar-days",
        "pitch": "Planifiez vos événements, activités et intervenants dans un programme clair.",
    },
    "registration_access": {
        "icon": "ticket",
        "pitch": "Inscriptions, billets QR, contrôle des entrées et capacité des accès.",
    },
    "resources_operations": {
        "icon": "boxes",
        "pitch": "Lieux, matériel et allocations de ressources pour chaque événement.",
    },
    "sponsors_finance": {
        "icon": "wallet",
        "pitch": "Sponsors, partenariats, budgets prévisionnels et dépenses.",
    },
    "communication_media": {
        "icon": "megaphone",
        "pitch": "Communiqués, dossiers de presse, médias et publications.",
    },
}


def _decorate(module):
    presentation = MODULE_PRESENTATION.get(module["app_name"], {})
    return {
        **module,
        "icon": presentation.get("icon", "layers"),
        "pitch": presentation.get("pitch", module["summary"]),
    }


def get_modules():
    from communication_media.entities import MODULE as communication
    from events_program.entities import MODULE as events
    from registration_access.entities import MODULE as registration
    from resources_operations.entities import MODULE as resources
    from sponsors_finance.entities import MODULE as sponsors

    return [
        _decorate(module)
        for module in (events, registration, resources, sponsors, communication)
    ]


def get_users_module():
    from users_teams.entities import MODULE as users

    return _decorate(users)
