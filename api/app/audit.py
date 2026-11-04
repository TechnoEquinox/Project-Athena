from typing import Any

from .extensions import db
from .models import AppUser, AuditLog

# Detail keys containing any of these are refused, so secrets can't reach the log
FORBIDDEN_KEY_PARTS = ("password", "token", "secret", "hash")


def _check_keys(detail: dict) -> None:
    for key, value in detail.items():
        if any(part in str(key).lower() for part in FORBIDDEN_KEY_PARTS):
            raise ValueError(f"Refusing to audit a field named {key!r}")
        if isinstance(value, dict):
            _check_keys(value)


def record(
    action: str,
    *,
    actor: AppUser | None = None,
    target_type: str | None = None,
    target_id: int | str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit entry to the current transaction. The caller commits."""
    if detail:
        _check_keys(detail)
    entry = AuditLog(
        action=action,
        actor_user_id=actor.user_id if actor else None,
        actor_username=actor.username if actor else None,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail,
    )
    db.session.add(entry)
    return entry