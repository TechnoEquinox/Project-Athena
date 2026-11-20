# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

import os
from zoneinfo import ZoneInfo

def _encryption_keys() -> list[str]:
    keys = [k.strip() for k in os.environ["TOTP_ENCRYPTION_KEY"].split(",") if k.strip()]
    if not keys:
        raise RuntimeError("TOTP_ENCRYPTION_KEY is empty")
    return keys

def parse_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (KeyError, ValueError):
        raise RuntimeError(f"LIBRARY_TIMEZONE {name!r} is not a valid time zone name") from None
    return name

def parse_fiscal_month(text: str) -> int:
    try:
        month = int(text)
    except ValueError:
        month = 0
    if not 1 <= month <= 12:
        raise RuntimeError("FISCAL_YEAR_START_MONTH must be a number from 1 to 12")
    return month

class Config:
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    AUTH_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "true").lower() != "false"
    TOTP_ENCRYPTION_KEYS = _encryption_keys()
    TOTP_REQUIRED_ROLES = tuple(
        r.strip() for r in os.environ.get("TOTP_REQUIRED_ROLES", "admin,manager").split(",") if r.strip()
    )
    PROXY_HOPS = int(os.environ.get("PROXY_HOPS", "0"))
    RETENTION_DAYS = max(1, int(os.environ.get("RETENTION_DAYS", "30")))
    AGENT_DIR = os.environ.get("AGENT_DIR", "/agent")   # shared folder for the server agent
    LIBRARY_TIMEZONE = parse_timezone(os.environ.get("LIBRARY_TIMEZONE", "America/New_York"))
    FISCAL_YEAR_START_MONTH = parse_fiscal_month(os.environ.get("FISCAL_YEAR_START_MONTH", "7"))