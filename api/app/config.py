import os

def _encryption_keys() -> list[str]:
    keys = [k.strip() for k in os.environ["TOTP_ENCRYPTION_KEY"].split(",") if k.strip()]
    if not keys:
        raise RuntimeError("TOTP_ENCRYPTION_KEY is empty")
    return keys

class Config:
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    AUTH_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "true").lower() != "false"
    TOTP_ENCRYPTION_KEYS = _encryption_keys()
    TOTP_REQUIRED_ROLES = tuple(
        r.strip() for r in os.environ.get("TOTP_REQUIRED_ROLES", "admin,manager").split(",") if r.strip()
    )