MODULE = {
    "code": "M4",
    "title": "Resources & Operations",
    "app_name": "resources_operations",
    "summary": "Lieux, ressources et allocations.",
    "entities": [
        {"slug": "venues", "name": "Lieu", "fields": ["Id_venue", "Name", "Type", "Address", "City", "Latitude", "Longitude", "Capacity", "Surface", "Parking_capacity", "Accessibility"]},
        {"slug": "resources", "name": "Ressource", "fields": ["Id_resource", "Name", "Type", "Quantity", "Unit_cost", "Location"]},
        {"slug": "resource-allocations", "name": "Allocation de ressource", "fields": ["Id_allocation", "Id_resource", "Id_event", "Quantity", "Start_time", "End_time"]},
    ],
}
