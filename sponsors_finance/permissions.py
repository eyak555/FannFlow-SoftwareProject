def can_manage_finance(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (
            getattr(user, "is_administrator", False)
            or getattr(user, "business_role", "") == "responsable_sponsors"
        )
    )
