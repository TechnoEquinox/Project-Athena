# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

import re
from datetime import date, datetime, timezone
from .models import CALL_STATUSES

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
ZIP_RE = re.compile(r"\d{5}")


class ValidationError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _text(value, field: str, *, required: bool, max_len: int) -> str | None:
    if value is None:
        if required:
            raise ValidationError(field, "This field is required.")
        return None
    if not isinstance(value, str):
        raise ValidationError(field, "Must be text.")
    value = value.strip()
    if not value:
        if required:
            raise ValidationError(field, "This field is required.")
        return None
    if len(value) > max_len:
        raise ValidationError(field, f"Must be at most {max_len} characters.")
    if not value.isprintable():
        raise ValidationError(field, "Contains invalid characters.")
    return value


def _required(field: str, max_len: int):
    return lambda v: _text(v, field, required=True, max_len=max_len)


def _optional(field: str, max_len: int):
    return lambda v: _text(v, field, required=False, max_len=max_len)


def clean_phone(value) -> str | None:
    text = _text(value, "phone", required=False, max_len=40)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValidationError("phone", "Must be a 10-digit phone number.")
    return digits


def clean_email(value) -> str | None:
    text = _text(value, "email", required=False, max_len=254)
    if text is None:
        return None
    text = text.lower()
    if not EMAIL_RE.fullmatch(text):
        raise ValidationError("email", "Must be a valid email address.")
    return text


def clean_zipcode(value) -> str | None:
    text = _text(value, "zipcode", required=False, max_len=10)
    if text is None:
        return None
    if not ZIP_RE.fullmatch(text):
        raise ValidationError("zipcode", "Must be a 5-digit ZIP code.")
    return text


def clean_languages(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError("languages", "Must be a list.")
    if len(value) > 10:
        raise ValidationError("languages", "At most 10 languages.")
    seen, out = set(), []
    for item in value:
        lang = _text(item, "languages", required=True, max_len=50)
        assert lang is not None
        if lang.lower() not in seen:
            seen.add(lang.lower())
            out.append(lang)
    return out


CLIENT_CLEANERS = {
    "first_name": _required("first_name", 100),
    "last_name": _required("last_name", 100),
    "phone": clean_phone,
    "email": clean_email,
    "zipcode": clean_zipcode,
    "languages": clean_languages,
}

DEVICE_CLEANERS = {
    "device_type": _required("device_type", 50),
    "description": _optional("description", 200),
}


def _clean(data: dict, cleaners: dict, required: tuple[str, ...], partial: bool) -> dict:
    for key in data:
        if key not in cleaners:
            raise ValidationError(str(key), "Unknown field.")
    out = {key: cleaners[key](value) for key, value in data.items()}
    if not partial:
        for key in required:
            if key not in out:
                raise ValidationError(key, "This field is required.")
    return out


def clean_client(data: dict, *, partial: bool) -> dict:
    return _clean(data, CLIENT_CLEANERS, ("first_name", "last_name"), partial)


def clean_device(data: dict, *, partial: bool) -> dict:
    return _clean(data, DEVICE_CLEANERS, ("device_type",), partial)

def clean_location(data: dict) -> dict:
    for key in data:
        if key != "name":
            raise ValidationError(str(key), "Unknown field.")
    text = _text(data.get("name"), "name", required=True, max_len=100)
    assert text is not None
    return {"name": " ".join(text.split())}   # collapse runs of spaces

def _int(value, field: str, *, low: int = 1, high: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(field, "Must be a whole number.")
    if value < low or (high is not None and value > high):
        raise ValidationError(
            field, f"Must be between {low} and {high}." if high is not None else f"Must be at least {low}."
        )
    return value


def _timestamp(value, field: str = "appointment_at") -> datetime:
    if not isinstance(value, str):
        raise ValidationError(field, "Must be a date and time.")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValidationError(
            field, "Must be ISO 8601, like 2026-11-02T14:30:00-05:00."
        ) from None
    if parsed.tzinfo is None:
        raise ValidationError(field, "Must include a time zone offset.")
    return parsed.astimezone(timezone.utc)


def clean_notes(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("notes", "Must be text.")
    value = value.strip()
    if not value:
        return None
    if len(value) > 5000:
        raise ValidationError("notes", "Must be at most 5000 characters.")
    if not all(ch.isprintable() or ch in "\n\r\t" for ch in value):
        raise ValidationError("notes", "Contains invalid characters.")
    return value


def clean_device_ids(value) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError("device_ids", "Must be a list.")
    if len(value) > 10:
        raise ValidationError("device_ids", "At most 10 devices.")
    out: list[int] = []
    for item in value:
        item = _int(item, "device_ids")
        if item not in out:
            out.append(item)
    return sorted(out)

APPOINTMENT_CLEANERS = {
    "client_id": lambda v: _int(v, "client_id"),
    "appointment_at": _timestamp,
    "location_id": lambda v: _int(v, "location_id"),
    "length_minutes": lambda v: _int(v, "length_minutes", high=600),
    "notes": clean_notes,
    "tech_id": lambda v: _int(v, "tech_id"),
    "device_ids": clean_device_ids,
}

def clean_appointment(data: dict, *, partial: bool) -> dict:
    cleaners = dict(APPOINTMENT_CLEANERS)
    if partial:
        cleaners.pop("client_id")   # an appointment never moves to another client
    return _clean(
        data, cleaners, ("client_id", "appointment_at", "location_id", "length_minutes"), partial
    )

def normalize_status(value) -> str | None:
    """'NEEDS CALL', 'needs call' and 'needs_call' all become 'needs_call'. Junk becomes None."""
    if not isinstance(value, str):
        return None
    key = "_".join(value.strip().lower().split())
    return key if key in CALL_STATUSES else None

def clean_status(value) -> str:
    status = normalize_status(value)
    if status is None:
        raise ValidationError("status", "Must be one of: " + ", ".join(CALL_STATUSES) + ".")
    return status

CALL_CLEANERS = {
    "called_at": lambda v: _timestamp(v, "called_at"),
    "status": clean_status,
    "client_id": lambda v: None if v is None else _int(v, "client_id"),
    "client_first_name": _optional("client_first_name", 100),
    "client_last_name": _optional("client_last_name", 100),
    "phone": clean_phone,
    "notes": clean_notes,
    "tech_id": lambda v: _int(v, "tech_id"),
}

def clean_call(data: dict, *, partial: bool) -> dict:
    return _clean(data, CALL_CLEANERS, ("status",), partial)

def clean_start_date(value) -> date:
    if not isinstance(value, str):
        raise ValidationError("start_date", "Must be a date like 2026-11-09.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValidationError("start_date", "Must be a date like 2026-11-09.") from None

TECH_CLEANERS = {
    "first_name": _required("first_name", 100),
    "last_name": _required("last_name", 100),
    "start_date": clean_start_date,
}

def clean_tech(data: dict, *, partial: bool) -> dict:
    return _clean(data, TECH_CLEANERS, ("first_name", "last_name", "start_date"), partial)