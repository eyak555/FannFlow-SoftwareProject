MODULE = {
    "code": "M2",
    "title": "Events & Program",
    "app_name": "events_program",
    "summary": "Événements, activités et intervenants.",
    "entities": [
        {"slug": "events", "name": "Événement", "fields": ["Id_event", "Title", "Description", "Event_type", "Category", "Start_date", "End_date", "Registration_deadline", "Capacity", "Director_id", "Id_venue"]},
        {"slug": "activities", "name": "Activité", "fields": ["Id_activity", "Id_event", "Title", "Description", "Type", "Start_time", "End_time", "Capacity", "Room"]},
        {"slug": "speakers", "name": "Intervenant", "fields": ["Id_speaker", "Name", "Bio", "Organization", "Country", "Expertise"]},
        {"slug": "activity-speakers", "name": "Affectation intervenant", "fields": ["Id_activity", "Id_speaker"]},
    ],
}
