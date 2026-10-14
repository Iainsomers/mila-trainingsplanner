import re

from django.core.exceptions import ValidationError


class PasswordComplexityValidator:
    """Require a basic strong password for user-initiated password changes."""

    def validate(self, password, user=None):
        if len(password or "") < 8:
            raise ValidationError("Your password must contain at least 8 characters.")
        if not re.search(r"[A-Z]", password):
            raise ValidationError("Your password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", password):
            raise ValidationError("Your password must contain at least one lowercase letter.")
        if not re.search(r"\d", password):
            raise ValidationError("Your password must contain at least one number.")
        if not re.search(r"[^A-Za-z0-9]", password):
            raise ValidationError("Your password must contain at least one special character.")

    def get_help_text(self):
        return (
            "Your password must contain at least 8 characters, including an uppercase letter, "
            "a lowercase letter, a number and a special character."
        )

