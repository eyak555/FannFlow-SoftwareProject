from .permissions import can_administer_operations, is_operations_director


MODULE = {
    "code": "M4",
    "title": "Resources & Operations",
    "app_name": "resources_operations",
    "summary": "Gérez les lieux, l’inventaire et les réservations de matériel pour vos événements.",
    "entities": [
        {
            "slug": "venues",
            "name": "Lieu",
            "plural": "Lieux",
            "description": "Adresses, capacité d’accueil, parking et accessibilité PMR.",
            "create_label": "Ajouter un lieu",
            "search_label": "Nom, type ou adresse",
            "filter_label": "Accessibilité",
            "filters": [("accessible", "Accessible PMR"), ("other", "Non accessible PMR")],
            "fields": ["Id_venue", "Name", "Type", "Address", "Latitude", "Longitude",
                       "Capacity", "Surface", "Parking_capacity", "Accessibility"],
        },
        {
            "slug": "resources",
            "name": "Ressource",
            "plural": "Ressources",
            "description": "Quantités en stock, coûts unitaires et emplacements.",
            "create_label": "Ajouter une ressource",
            "search_label": "Nom, type ou emplacement",
            "filter_label": "Stock ou état",
            "filters": [("in-stock", "En stock"), ("out-of-stock", "Stock épuisé"),
                        ("maintenance", "En maintenance"), ("unavailable", "Hors service")],
            "fields": ["Id_resource", "Name", "Type", "Quantity", "Unit_cost", "Location"],
        },
        {
            "slug": "resource-allocations",
            "name": "Allocation de ressource",
            "plural": "Allocations",
            "description": "Réservations par événement, quantité et période.",
            "create_label": "Créer une allocation",
            "search_label": "Ressource, nom ou numéro d’événement",
            "filter_label": "Période",
            "filters": [("upcoming", "À venir"), ("active", "En cours"), ("ended", "Terminée")],
            "fields": ["Id_allocation", "Id_resource", "Id_event", "Quantity", "Start_time", "End_time"],
        },
    ],
}


def get_accessible_sections(user):
    if can_administer_operations(user):
        return MODULE["entities"]
    if is_operations_director(user):
        return [entity for entity in MODULE["entities"] if entity["slug"] != "resources"]
    return []
