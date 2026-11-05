import re

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