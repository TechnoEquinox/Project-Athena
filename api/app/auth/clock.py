# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

from datetime import datetime, timezone

def now() -> datetime:
    return datetime.now(timezone.utc)