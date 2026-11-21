MODULE = {
    "code": "M5",
    "title": "Sponsors & Finance",
    "app_name": "sponsors_finance",
    "summary": "Sponsors, partenariats, budgets et dépenses.",
    "entities": [
        {"slug": "sponsors", "name": "Sponsor", "fields": ["Id_sponsor", "Company_name", "Industry", "Email", "Phone", "Address", "Target_audience"]},
        {"slug": "sponsorship-packages", "name": "Package de sponsoring", "fields": ["Id_package", "Name", "Description", "Price", "Benefits"]},
        {"slug": "partnerships", "name": "Partenariat", "fields": ["Id_partnership", "Id_sponsor", "Id_event", "Id_package", "Amount", "Start_date", "End_date"]},
        {"slug": "expenses", "name": "Dépense", "fields": ["Id_expense", "Id_event", "Category", "Amount", "Date", "Description"]},
        {"slug": "budgets", "name": "Budget", "fields": ["Id_budget", "Id_event", "Planned_amount"]},
    ],
}
