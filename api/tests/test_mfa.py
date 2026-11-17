# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import datetime, timedelta, timezone

import pyotp
from sqlalchemy import func, select

from app.auth import mfa, settings, totp
from app.auth.sessions import hash_token
from app.extensions import db
from app.models import AppUser, MfaChallenge, RecoveryCode

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
STEP = int(NOW.timestamp()) // 30


def make_user(username="boss", enrolled=True):
    user = AppUser(username=username, password_hash="x", role="admin")
    secret = None
    if enrolled:
        secret = totp.generate_secret()
        user.totp_secret_encrypted = totp.encrypt_secret(secret)
        user.totp_enabled = True
    db.session.add(user)
    db.session.commit()
    return user, secret


def count(model):
    return db.session.scalar(select(func.count()).select_from(model))


# ---------- challenges ----------

def test_challenge_stores_only_hash(app):
    with app.app_context():
        user, _ = make_user()
        token = mfa.create_challenge(user, NOW)
        db.session.commit()
        row = db.session.scalars(select(MfaChallenge)).one()
        assert row.token_hash == hash_token(token) != token
        assert row.expires_at == NOW + settings.MFA_CHALLENGE_TTL


def test_challenge_lookup(app):
    with app.app_context():
        user, _ = make_user()
        token = mfa.create_challenge(user, NOW)
        db.session.commit()
        assert mfa.lookup_challenge(token, NOW + timedelta(minutes=1)).user_id == user.user_id
        assert mfa.lookup_challenge("nope", NOW) is None
        assert mfa.lookup_challenge("", NOW) is None
        assert mfa.lookup_challenge(None, NOW) is None


def test_challenge_expires_after_five_minutes(app):
    with app.app_context():
        user, _ = make_user()
        token = mfa.create_challenge(user, NOW)
        db.session.commit()
        assert mfa.lookup_challenge(token, NOW + timedelta(minutes=4, seconds=59)) is not None
        assert mfa.lookup_challenge(token, NOW + timedelta(minutes=5)) is None
        assert count(MfaChallenge) == 0


def test_revoke_challenges_only_hits_that_user(app):
    with app.app_context():
        a, _ = make_user("a")
        b, _ = make_user("b")
        mfa.create_challenge(a, NOW)
        mfa.create_challenge(a, NOW)
        keep = mfa.create_challenge(b, NOW)
        db.session.commit()
        assert mfa.revoke_challenges(a.user_id) == 2
        assert mfa.lookup_challenge(keep, NOW) is not None


def test_purge_expired_challenges(app):
    with app.app_context():
        user, _ = make_user()
        mfa.create_challenge(user, NOW)
        fresh = mfa.create_challenge(user, NOW + timedelta(minutes=3))
        db.session.commit()
        later = NOW + timedelta(minutes=6)
        assert mfa.purge_expired_challenges(later) == 1
        assert mfa.lookup_challenge(fresh, later) is not None


# ---------- totp codes ----------

def test_totp_code_works_once(app):
    with app.app_context():
        user, secret = make_user()
        code = pyotp.TOTP(secret).generate_otp(STEP)
        assert mfa.verify_second_factor(user, code=code, now=NOW) == "totp"
        assert user.totp_last_used_step == STEP
        assert mfa.verify_second_factor(user, code=code, now=NOW) is None


def test_wrong_code_does_not_burn_a_step(app):
    with app.app_context():
        user, secret = make_user()
        valid = {pyotp.TOTP(secret).generate_otp(s) for s in (STEP - 1, STEP, STEP + 1)}
        bad = next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)
        assert mfa.verify_second_factor(user, code=bad, now=NOW) is None
        assert user.totp_last_used_step is None


def test_user_without_a_secret_cannot_verify(app):
    with app.app_context():
        user, _ = make_user(enrolled=False)
        assert mfa.verify_second_factor(user, code="123456", now=NOW) is None


def test_no_factor_supplied(app):
    with app.app_context():
        user, _ = make_user()
        assert mfa.verify_second_factor(user, now=NOW) is None


# ---------- recovery codes ----------

def test_recovery_codes_are_stored_hashed(app):
    with app.app_context():
        user, _ = make_user()
        codes = mfa.issue_recovery_codes(user)
        db.session.commit()
        rows = db.session.scalars(select(RecoveryCode)).all()
        assert len(rows) == 10
        assert {r.code_hash for r in rows} == {totp.hash_recovery_code(c) for c in codes}
        assert all(len(r.code_hash) == 64 for r in rows)


def test_reissuing_replaces_the_old_set(app):
    with app.app_context():
        user, _ = make_user()
        old = mfa.issue_recovery_codes(user)
        db.session.commit()
        new = mfa.issue_recovery_codes(user)
        db.session.commit()
        assert count(RecoveryCode) == 10
        assert mfa.verify_second_factor(user, recovery_code=old[0], now=NOW) is None
        assert mfa.verify_second_factor(user, recovery_code=new[0], now=NOW) == "recovery"


def test_recovery_code_is_single_use(app):
    with app.app_context():
        user, _ = make_user()
        codes = mfa.issue_recovery_codes(user)
        db.session.commit()
        assert mfa.verify_second_factor(user, recovery_code=codes[0], now=NOW) == "recovery"
        db.session.commit()
        assert mfa.verify_second_factor(user, recovery_code=codes[0], now=NOW) is None
        assert mfa.remaining_recovery_codes(user.user_id) == 9


def test_recovery_code_formatting_is_forgiven(app):
    with app.app_context():
        user, _ = make_user()
        codes = mfa.issue_recovery_codes(user)
        db.session.commit()
        sloppy = codes[0].replace("-", " ").upper()
        assert mfa.verify_second_factor(user, recovery_code=sloppy, now=NOW) == "recovery"


def test_unknown_recovery_code(app):
    with app.app_context():
        user, _ = make_user()
        mfa.issue_recovery_codes(user)
        db.session.commit()
        assert mfa.verify_second_factor(user, recovery_code="aaaa-bbbb-cccc-dddd", now=NOW) is None


def test_recovery_codes_belong_to_one_user(app):
    with app.app_context():
        a, _ = make_user("a")
        b, _ = make_user("b")
        codes_a = mfa.issue_recovery_codes(a)
        mfa.issue_recovery_codes(b)
        db.session.commit()
        assert mfa.verify_second_factor(b, recovery_code=codes_a[0], now=NOW) is None
        assert mfa.verify_second_factor(a, recovery_code=codes_a[0], now=NOW) == "recovery"


# ---------- disable and cascade ----------

def test_disable_clears_everything(app):
    with app.app_context():
        user, _ = make_user()
        user.totp_last_used_step = 5
        mfa.issue_recovery_codes(user)
        mfa.create_challenge(user, NOW)
        db.session.commit()
        mfa.disable_totp(user)
        db.session.commit()
        assert user.totp_enabled is False
        assert user.totp_secret_encrypted is None
        assert user.totp_last_used_step is None
        assert count(RecoveryCode) == 0 and count(MfaChallenge) == 0


def test_rows_die_with_the_user(app):
    with app.app_context():
        user, _ = make_user()
        mfa.issue_recovery_codes(user)
        mfa.create_challenge(user, NOW)
        db.session.commit()
        db.session.delete(user)
        db.session.commit()
        assert count(RecoveryCode) == 0 and count(MfaChallenge) == 0