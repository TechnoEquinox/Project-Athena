# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

import pytest
from argon2 import PasswordHasher

from app.auth.passwords import (
    PasswordPolicyError, fake_verify, hash_password, needs_rehash,
    validate_password, verify_password,
)

def test_hash_is_argon2id():
    assert hash_password("correct horse battery").startswith("$argon2id$")


def test_same_password_hashes_differently():
    assert hash_password("correct horse battery") != hash_password("correct horse battery")


def test_verify_correct_and_wrong():
    h = hash_password("correct horse battery")
    assert verify_password(h, "correct horse battery") is True
    assert verify_password(h, "correct horse batterY") is False


def test_verify_garbage_hash_is_false_not_error():
    assert verify_password("not-a-hash", "whatever") is False


def test_minimum_length():
    with pytest.raises(PasswordPolicyError):
        validate_password("a" * 11)
    validate_password("a" * 12)


def test_maximum_length():
    validate_password("a" * 128)
    with pytest.raises(PasswordPolicyError):
        validate_password("a" * 129)


def test_spaces_and_unicode_allowed():
    validate_password("pässwörd with spaces ✓✓")


def test_hash_password_enforces_policy():
    with pytest.raises(PasswordPolicyError):
        hash_password("short")


def test_needs_rehash():
    assert needs_rehash(hash_password("correct horse battery")) is False
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("correct horse battery")
    assert needs_rehash(weak) is True


def test_fake_verify_always_false():
    assert fake_verify("anything at all") is False