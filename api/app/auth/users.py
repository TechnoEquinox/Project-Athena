# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

import re

from sqlalchemy import select

from ..extensions import db
from ..models import ROLES, AppUser, Tech
from .passwords import hash_password

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,64}$")

class UserCreationError(ValueError):
    pass

def create_user(username: str, password: str, role: str, tech_id: int | None = None) -> AppUser:
    """Validate and add a new login.
    
    Raises UserCreationError, or PasswordPolicyError for a bad password.
    """
    if role not in ROLES:
        raise UserCreationError(f"Role must be one of: {', '.join(ROLES)}.")
    if username != username.lower():
        raise UserCreationError("Username must be lowercase.")
    if not USERNAME_RE.fullmatch(username):
        raise UserCreationError(
            "Username must be 3-64 characters: lowercase letters, digits, '.', '_', or '-'"
        )
    if role == "navigator" and tech_id is None:
        raise UserCreationError("Navigator accounts must be linked to a tech record.")
    if tech_id is not None:
        if db.session.get(Tech, tech_id) is None:
            raise UserCreationError(f"No tech record with id {tech_id}.")
        if db.session.scalar(select(AppUser.user_id).where(AppUser.tech_id == tech_id)) is not None:
            raise UserCreationError(f"Tech {tech_id} already has a login.")
    if db.session.scalar(select(AppUser.user_id).where(AppUser.username == username)) is not None:
        raise UserCreationError(f"Username {username} already exists.")
    
    user = AppUser(
        username=username,
        password_hash=hash_password(password),
        role=role,
        tech_id=tech_id
    )
    db.session.add(user)
    db.session.commit()
    return user