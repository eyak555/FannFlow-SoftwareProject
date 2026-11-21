MODULE = {
    "code": "M1",
    "title": "Users & Organization Teams",
    "app_name": "users_teams",
    "summary": "Utilisateurs, profils participants et équipes d’organisation.",
    "entities": [
        {"slug": "users", "name": "Utilisateur", "fields": ["Id_user", "First_name", "Last_name", "Email", "Password_hash", "Phone", "Address", "Role", "Profile_picture"]},
        {"slug": "participant-profiles", "name": "Profil participant", "fields": ["Id_profile", "Id_user", "Profession", "Organization", "Bio", "Interests", "Languages", "Experience"]},
        {"slug": "organization-teams", "name": "Équipe d’organisation", "fields": ["Id_team", "Name", "Team_type", "Description", "Leader_id"]},
        {"slug": "team-members", "name": "Membre d’équipe", "fields": ["Id_team_member", "Id_team", "Id_user", "Role_in_team"]},
        {"slug": "event-teams", "name": "Affectation d’équipe", "fields": ["Id_event_team", "Id_event", "Id_team", "Assigned_zone", "Start_date", "End_date"]},
    ],
}
