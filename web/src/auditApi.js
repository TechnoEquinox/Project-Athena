import { api, qs } from './api'

export function listAudit({ action, before_id, limit } = {}) {
  return api.get(`/api/admin/audit${qs({ action, before_id, limit })}`)
}