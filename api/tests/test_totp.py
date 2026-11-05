from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.auth import settings, totp
from app.models import AppUser

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
STEP = int(NOW.timestamp()) // 30


def code_for(secret, step):
    return pyotp.TOTP(secret).generate_otp(step)


def wrong_code(secret):
    valid = {code_for(secret, s) for s in (STEP - 1, STEP, STEP + 1)}
    return next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)


@pytest.fixture
def secret():
    return totp.generate_secret()


def test_settings_are_pinned():
    assert settings.TOTP_STEP_SECONDS == 30
    assert settings.TOTP_WINDOW == 1
    assert settings.MFA_CHALLENGE_TTL == timedelta(minutes=5)
    assert settings.RECOVERY_CODE_COUNT == 10


# ---------- secrets ----------

def test_secret_is_random_base32():
    a, b = totp.generate_secret(), totp.generate_secret()
    assert a != b and len(a) == 32
    pyotp.TOTP(a).now()   # raises if it isn't valid base32


def test_encrypt_round_trip_and_not_plaintext(app, secret):
    with app.app_context():
        stored = totp.encrypt_secret(secret)
        assert secret not in stored
        assert totp.decrypt_secret(stored) == secret


def test_encryption_is_randomized(app, secret):
    with app.app_context():
        assert totp.encrypt_secret(secret) != totp.encrypt_secret(secret)


def test_tampered_ciphertext_rejected(app, secret):
    with app.app_context():
        stored = totp.encrypt_secret(secret)
        tampered = stored[:-4] + ("AAAA" if not stored.endswith("AAAA") else "BBBB")
        with pytest.raises(InvalidToken):
            totp.decrypt_secret(tampered)


def test_wrong_key_rejected(app, secret, monkeypatch):
    with app.app_context():
        stored = totp.encrypt_secret(secret)
        monkeypatch.setitem(app.config, "TOTP_ENCRYPTION_KEYS", [Fernet.generate_key().decode()])
        with pytest.raises(InvalidToken):
            totp.decrypt_secret(stored)


def test_key_rotation(app, secret, monkeypatch):
    with app.app_context():
        old_key = app.config["TOTP_ENCRYPTION_KEYS"][0]
        stored = totp.encrypt_secret(secret)
        new_key = Fernet.generate_key().decode()

        # New key first, old key kept for decrypting: old data still readable
        monkeypatch.setitem(app.config, "TOTP_ENCRYPTION_KEYS", [new_key, old_key])
        assert totp.decrypt_secret(stored) == secret
        fresh = totp.encrypt_secret(secret)

        # Once the old key is dropped, only data written with the new key survives
        monkeypatch.setitem(app.config, "TOTP_ENCRYPTION_KEYS", [new_key])
        assert totp.decrypt_secret(fresh) == secret
        with pytest.raises(InvalidToken):
            totp.decrypt_secret(stored)


def test_no_keys_configured_is_an_error(app, secret, monkeypatch):
    with app.app_context():
        monkeypatch.setitem(app.config, "TOTP_ENCRYPTION_KEYS", [])
        with pytest.raises(RuntimeError):
            totp.encrypt_secret(secret)


def test_provisioning_uri(secret):
    uri = totp.provisioning_uri(secret, "boss")
    assert uri.startswith("otpauth://totp/")
    assert secret in uri and "boss" in uri and "issuer=Athena" in uri


# ---------- code verification ----------

def test_current_code_accepted(secret):
    assert totp.verify_code(secret, code_for(secret, STEP), NOW) == STEP


@pytest.mark.parametrize("offset", [-1, 1])
def test_one_step_of_drift_accepted(secret, offset):
    assert totp.verify_code(secret, code_for(secret, STEP + offset), NOW) == STEP + offset


@pytest.mark.parametrize("offset", [-2, 2])
def test_two_steps_away_rejected(secret, offset):
    assert totp.verify_code(secret, code_for(secret, STEP + offset), NOW) is None


def test_wrong_code_rejected(secret):
    assert totp.verify_code(secret, wrong_code(secret), NOW) is None


def test_replay_rejected(secret):
    assert totp.verify_code(secret, code_for(secret, STEP), NOW, last_used_step=STEP) is None


def test_code_older_than_last_used_rejected(secret):
    assert totp.verify_code(secret, code_for(secret, STEP - 1), NOW, last_used_step=STEP) is None


def test_newer_step_accepted_after_last_used(secret):
    assert totp.verify_code(secret, code_for(secret, STEP + 1), NOW, last_used_step=STEP) == STEP + 1


def test_spaces_in_code_are_ignored(secret):
    code = code_for(secret, STEP)
    assert totp.verify_code(secret, f"{code[:3]} {code[3:]}", NOW) == STEP


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "12 34 5", "١٢٣٤٥٦"])
def test_malformed_codes_rejected(secret, bad):
    assert totp.verify_code(secret, bad, NOW) is None


# ---------- recovery codes ----------

def test_recovery_codes_shape():
    codes = totp.generate_recovery_codes()
    assert len(codes) == 10 == len(set(codes))
    for code in codes:
        groups = code.split("-")
        assert len(groups) == 4 and all(len(g) == 4 for g in groups)
        assert set(code.replace("-", "")) <= set(settings.RECOVERY_ALPHABET)


def test_normalize_forgives_formatting():
    assert totp.normalize_recovery_code(" ABCD-efgh ijkm-NPQR ") == "abcdefghijkmnpqr"


def test_recovery_hash_ignores_formatting():
    a = totp.hash_recovery_code("abcd-efgh-ijkm-npqr")
    assert a == totp.hash_recovery_code("ABCD EFGH IJKM NPQR")
    assert len(a) == 64
    assert a != totp.hash_recovery_code("abcd-efgh-ijkm-npqs")


# ---------- enforcement flag ----------

def test_setup_required(app, monkeypatch):
    with app.app_context():
        monkeypatch.setitem(app.config, "TOTP_REQUIRED_ROLES", ("admin", "manager"))
        user = AppUser(username="x", password_hash="x", role="admin", totp_enabled=False)
        assert totp.setup_required(user) is True
        user.totp_enabled = True
        assert totp.setup_required(user) is False
        nav = AppUser(username="y", password_hash="x", role="navigator", totp_enabled=False)
        assert totp.setup_required(nav) is False
        monkeypatch.setitem(app.config, "TOTP_REQUIRED_ROLES", ())
        user.totp_enabled = False
        assert totp.setup_required(user) is False