// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { api, qs } from './api'

export function listAudit({ action, before_id, limit } = {}) {
  return api.get(`/api/admin/audit${qs({ action, before_id, limit })}`)
}