MODULE = {
    "code": "M6",
    "title": "Communication & Media",
    "app_name": "communication_media",
    "summary": "Communication officielle, dossiers de presse, publications et médias.",
    "entities": [
        {"slug": "communications", "name": "Communication", "fields": ["Id_comm", "Titre", "Contenu", "Type", "Date_publication", "Langue", "Statut", "Id_event"]},
        {"slug": "media", "name": "Média", "fields": ["Id_media", "Nom", "Type", "Url", "Format", "Taille", "Date_upload", "Id_event", "Id_comm"]},
        {"slug": "press-kits", "name": "Dossier de presse", "fields": ["Id_kit", "Titre", "Description", "Date_creation", "Id_event"]},
        {"slug": "media-contacts", "name": "Contact média", "fields": ["Id_contact", "Nom", "Organisation", "Email", "Téléphone", "Rôle"]},
        {"slug": "publications", "name": "Publication", "fields": ["Id_publication", "Plateforme", "Contenu", "Date_publication", "Statut", "Id_event"]},
    ],
}
