COACH_TOOLS_ONLY_USERNAMES = {"coachtools"}


def is_coach_tools_only_user(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return str(getattr(user, "username", "")).strip().lower() in COACH_TOOLS_ONLY_USERNAMES
