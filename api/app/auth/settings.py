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