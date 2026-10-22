"""Password strength policy.

Shared by registration and by the self-service password change so that the
same rules apply on both paths.
"""

from app.core.exceptions import ValidationError

MIN_PASSWORD_LENGTH = 12
SPECIAL_CHARACTERS = "!@#$%^&*()_+-=[]{}|;:,.<>?"

COMMON_WEAK_PASSWORDS = frozenset(
    {
        "password123",
        "password12",
        "qwerty123",
        "admin123",
        "welcome123",
        "changeme123",
        "letmein123",
        "monkey123",
        "dragon123",
        "master123",
    }
)


def validate_password_strength(
    password: str,
    username: str | None = None,
    email: str | None = None,
) -> None:
    """Raise ``ValidationError`` when the password does not meet the policy.

    The policy requires length, mixed case, a digit, a special character, and
    that the password does not embed the username or the email local part.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            {"field": "new_password"},
        )
    if password.lower() == password or password.upper() == password:
        raise ValidationError("Password must contain mixed case", {"field": "new_password"})
    if not any(c.isdigit() for c in password):
        raise ValidationError("Password must contain at least one digit", {"field": "new_password"})
    if not any(c in SPECIAL_CHARACTERS for c in password):
        raise ValidationError(
            "Password must contain at least one special character", {"field": "new_password"}
        )
    if username and username.lower() in password.lower():
        raise ValidationError("Password must not contain username", {"field": "new_password"})
    if email and email.split("@")[0].lower() in password.lower():
        raise ValidationError("Password must not contain email", {"field": "new_password"})
    if password.lower() in COMMON_WEAK_PASSWORDS:
        raise ValidationError(
            "Password is too common - choose a stronger password", {"field": "new_password"}
        )
