# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import date

import click
from sqlalchemy import select

from .auth import clock
from .auth import mfa
from .auth.accounts import unlock_user
from .auth.passwords import PasswordPolicyError
from .auth.sessions import purge_expired, revoke_user_sessions
from .auth.users import UserCreationError, create_user
from .extensions import db
from .models import ROLES, AppUser, Tech
from .retention import purge_deleted, retention_days
from . import audit


def _make_user(username: str, role: str, tech_id: int | None) -> None:
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    try:
        user = create_user(username, password, role, tech_id)
        audit.record("user_created", target_type="user", target_id=user.user_id,
                     detail={"role": role, "via": "cli"})
        db.session.commit()
    except (UserCreationError, PasswordPolicyError) as exc:
        db.session.rollback()
        raise click.ClickException(str(exc))
    click.echo(f"Created {role} account '{user.username}'.")


def register_cli(app):
    @app.cli.command("create-user")
    @click.argument("username")
    @click.option("--role", type=click.Choice(ROLES), required=True)
    @click.option("--tech-id", type=int, default=None, help="Tech record to link (required for navigators).")
    def create_user_command(username, role, tech_id):
        """Create a login account."""
        if role == "navigator" and tech_id is None:
            raise click.UsageError("Navigator accounts need --tech-id (see create-tech).")
        _make_user(username, role, tech_id)

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.option("--tech-id", type=int, default=None, help="Optionally link to a tech record.")
    def create_admin_command(username, tech_id):
        """Shortcut for create-user --role admin."""
        _make_user(username, "admin", tech_id)

    @app.cli.command("create-tech")
    @click.argument("first_name")
    @click.argument("last_name")
    @click.option("--start-date", type=click.DateTime(formats=["%Y-%m-%d"]), default=None,
                  help="YYYY-MM-DD (defaults to today).")
    def create_tech_command(first_name, last_name, start_date):
        """Create a tech record."""
        tech = Tech(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            start_date=start_date.date() if start_date else date.today(),
        )
        db.session.add(tech)
        db.session.commit()
        click.echo(f"Created tech #{tech.tech_id}: {tech.first_name} {tech.last_name}.")

    @app.cli.command("unlock-user")
    @click.argument("username")
    def unlock_user_command(username):
        """Break-glass reset: clear a lockout and log the user out."""
        user = db.session.scalar(
            select(AppUser).where(AppUser.username == username.strip().lower())
        )
        if user is None:
            raise click.ClickException(f"No such user: {username}")
        unlock_user(user)
        audit.record("user_unlocked", target_type="user", target_id=user.user_id,
                     detail={"via": "cli"})
        db.session.commit()
        click.echo(f"Unlocked '{user.username}' and ended their session.")

    @app.cli.command("purge-sessions")
    def purge_sessions_command():
        """Delete expired sessions and two-factor challenges."""
        now = clock.now()
        sessions = purge_expired(now)
        challenges = mfa.purge_expired_challenges(now)
        db.session.commit()
        click.echo(f"Purged {sessions} expired session(s).")
        click.echo(f"Purged {challenges} expired challenge(s).")

    @app.cli.command("reset-totp")
    @click.argument("username")
    def reset_totp_command(username):
        """Remove a user's two factor setup and end their session."""
        user = db.session.scalar(
            select(AppUser).where(AppUser.username == username.strip().lower())
        )
        if user is None:
            raise click.ClickException(f"No such user: {username}")
        mfa.disable_totp(user)
        revoke_user_sessions(user.user_id)
        audit.record("user_totp_reset", target_type="user", target_id=user.user_id, detail={"via": "cli"})
        db.session.commit()
        click.echo(f"Removed two-factor for '{user.username}' and ended their current session.")

    @app.cli.command("purge-deleted")
    @click.option("--days", type=click.IntRange(min=1), default=None, help="Override the retention period (default: RETENTION_DAYS, normally 30).")
    def purge_deleted_command(days):
        """Permanently delete records soft-deleted longer ago than the retention period."""
        days = days if days is not None else retention_days()
        counts = purge_deleted(clock.now(), days)
        if sum(counts.values()):
            audit.record("retention_purge", detail={"via": "cli", "days": days, **counts})
        db.session.commit()
        click.echo(
            f"Permanently deleted records older than {days} days: "
            f"{counts['clients']} client(s), {counts['appointments']} appointment(s), "
            f"{counts['call_logs']} call log(s), {counts['devices']} device(s)."
        )