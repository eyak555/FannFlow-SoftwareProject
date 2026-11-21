"""Agrège les six modules déjà décrits dans le cahier des charges.

Les données de chaque module vivent dans ``<app>/entities.py``.
Ce registre ne fait que les exposer au gabarit et à la navigation.
"""


def get_modules():
    from communication_media.entities import MODULE as communication
    from events_program.entities import MODULE as events
    from registration_access.entities import MODULE as registration
    from resources_operations.entities import MODULE as resources
    from sponsors_finance.entities import MODULE as sponsors

    return [
        events,
        registration,
        resources,
        sponsors,
        communication,
    ]
