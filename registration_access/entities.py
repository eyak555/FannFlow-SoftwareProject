MODULE = {
    "code": "M3",
    "title": "Registration & Access",
    "app_name": "registration_access",
    "summary": "Inscriptions, billets, présences et points d’accès.",
    "entities": [
        {"slug": "registrations", "name": "Inscription", "fields": ["Id_registration", "Id_user", "Id_event", "Registration_date", "Status", "Ticket_type", "Payment_status"]},
        {"slug": "tickets", "name": "Billet", "fields": ["Id_ticket", "Id_registration", "Qr_code", "Price", "Category", "Status"]},
        {"slug": "attendances", "name": "Présence", "fields": ["Id_attendance", "Id_ticket", "Check_in", "Check_out", "Gate"]},
        {"slug": "access-points", "name": "Point d’accès", "fields": ["Id_access", "Id_event", "Name", "Location", "Capacity"]},
    ],
}
