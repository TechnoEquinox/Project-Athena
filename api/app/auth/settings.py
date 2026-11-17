# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import timedelta

# Sessions
IDLE_TIMEOUT = timedelta(minutes=30)
ABSOLUTE_TIMEOUT = timedelta(hours=8)

# Passwords
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128           # guard against large inputs

# Lockout
LOCK_AFTER_FAILURES = 5             # first timed lock
ADMIN_RESET_AT_FAILURES = 10        # permanent until an admin resets
BASE_LOCK = timedelta(minutes=5)    # doubles after each further auth failure

# Timeout
TOUCH_INTERVAL = timedelta(seconds=60)  # don't write the last_seen_at more often than this
TOKEN_BYTES = 32                        # 256 bits of randomness per token

# Cookies and CSRF
COOKIE_NAME = "athena_session"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Two-factor authentication (TOTP)
TOTP_STEP_SECONDS = 30
TOTP_WINDOW = 1                       # accept one step either side (30 s of clock drift)
TOTP_ISSUER = "Athena"
MFA_CHALLENGE_TTL = timedelta(minutes=5)
MFA_COOKIE_NAME = "athena_mfa"
RECOVERY_CODE_COUNT = 10
RECOVERY_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"   # 32 symbols, no l, o, 0 or 1
RECOVERY_GROUPS = 4
RECOVERY_GROUP_LEN = 4                # 16 symbols = 80 bits per code

# A required-role user without 2FA may only reach these until they enroll
MFA_SETUP_ENDPOINTS = frozenset({"auth.me", "auth.logout", "auth.totp_setup", "auth.totp_enable"})