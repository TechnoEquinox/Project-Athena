import { techLabel } from './appointments'

// ---------- roles and users ----------

export const ROLE_OPTIONS = [
  { value: 'admin', label: 'Admin' },
  { value: 'manager', label: 'Manager' },
  { value: 'navigator', label: 'Navigator' },
]

export const roleLabel = (role) => ROLE_OPTIONS.find((r) => r.value === role)?.label ?? role ?? ''

export function userStatus(user) {
  if (!user.is_active) return { label: 'Inactive', severity: 'secondary' }
  if (user.lockout_requires_admin) return { label: 'Locked (admin reset needed)', severity: 'danger' }
  if (user.locked) return { label: 'Locked', severity: 'warn' }
  return { label: 'Active', severity: 'success' }
}

/** The first thing wrong with a new-user form, or an empty string. */
export function userFormProblem(form) {
  const username = form.username.trim().toLowerCase()
  if (username.length < 3) return 'Username must be at least 3 characters.'
  if (!/^[a-z0-9._-]{3,64}$/.test(username)) {
    return 'Username can use lowercase letters, digits, ".", "_" and "-", up to 64 characters.'
  }
  if (!form.role) return 'Choose a role.'
  if (form.role === 'navigator' && form.tech_id == null) return 'A navigator needs a tech record.'
  if (form.password.length < 12) return 'Password must be at least 12 characters.'
  return ''
}

export function buildUserPayload(form) {
  const out = {
    username: form.username.trim().toLowerCase(),
    password: form.password,   // exactly as typed: spaces are allowed
    role: form.role,
  }
  if (form.tech_id != null) out.tech_id = form.tech_id
  return out
}

/** Active techs that don't have a login yet. */
export function linkableTechs(techs) {
  return techs
    .filter((t) => t.is_active && !t.login_role)
    .map((t) => ({ tech_id: t.tech_id, label: techLabel(t) }))
}

export function techName(techs, id) {
  const tech = techs.find((t) => t.tech_id === id)
  return tech ? `${tech.first_name} ${tech.last_name}` : ''
}

// ---------- plain dates (tech start date) ----------

const two = (n) => String(n).padStart(2, '0')

export const formatYmd = (d) => `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`

export function parseYmd(text) {
  const [y, m, d] = text.split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** A plain date shown in local format. Parsed locally, so it never shifts by a day. */
export const showDate = (ymd) => (ymd ? parseYmd(ymd).toLocaleDateString() : '')

// ---------- techs ----------

export function emptyTechForm(tech = null, { now = new Date() } = {}) {
  if (tech) {
    return { first_name: tech.first_name, last_name: tech.last_name, start_date: parseYmd(tech.start_date) }
  }
  return {
    first_name: '', last_name: '',
    start_date: new Date(now.getFullYear(), now.getMonth(), now.getDate()),
  }
}

/** Create: everything. Edit: only the fields that changed. */
export function buildTechPayload(form, original = null) {
  const next = {
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    start_date: formatYmd(form.start_date),
  }
  if (!original) return next
  const out = {}
  for (const key of Object.keys(next)) {
    if (next[key] !== original[key]) out[key] = next[key]
  }
  return out
}

// ---------- restore ----------

const DAY = 24 * 60 * 60 * 1000

export function restoreWindowText(until, now = new Date()) {
  const ms = new Date(until).getTime() - now.getTime()
  if (ms <= 0) return 'Expired'
  if (ms < DAY) return 'Less than a day'
  const days = Math.floor(ms / DAY)
  return `${days} day${days === 1 ? '' : 's'}`
}

export function restoreSeverity(until, now = new Date()) {
  const ms = new Date(until).getTime() - now.getTime()
  if (ms < 3 * DAY) return 'danger'
  if (ms < 7 * DAY) return 'warn'
  return 'secondary'
}

export const statusText = (status) => String(status).replace(/_/g, ' ').toUpperCase()

// ---------- audit log ----------

export const AUDIT_ACTIONS = [
  'login_success', 'login_failed', 'login_mfa_required', 'account_locked', 'logout',
  'password_changed', 'password_change_failed',
  'totp_setup_started', 'totp_setup_failed', 'totp_enabled', 'totp_disabled', 'totp_disable_failed',
  'recovery_codes_regenerated', 'recovery_codes_regenerate_failed',
  'user_created', 'user_deactivated', 'user_reactivated', 'user_unlocked',
  'user_password_reset', 'user_totp_reset',
  'client_created', 'client_updated', 'client_deleted', 'client_restored',
  'device_added', 'device_updated', 'device_removed', 'device_restored',
  'appointment_created', 'appointment_updated', 'appointment_deleted', 'appointment_restored',
  'call_created', 'call_updated', 'call_deleted', 'call_restored',
  'location_created', 'location_renamed', 'location_deactivated', 'location_reactivated',
  'tech_created', 'tech_updated', 'tech_deactivated', 'tech_reactivated',
  'retention_purge',
]

export function humanizeAction(action) {
  const words = action.split('_').map((w) => (w === 'totp' ? '2FA' : w))
  const text = words.join(' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export const actorLabel = (entry) => entry.actor_username ?? '—'

export const targetLabel = (entry) =>
  entry.target_type && entry.target_id ? `${entry.target_type} #${entry.target_id}` : ''

export function formatDetail(detail) {
  if (!detail || typeof detail !== 'object') return ''
  return Object.entries(detail)
    .map(([key, value]) => {
      const shown = Array.isArray(value)
        ? value.join(', ')
        : value !== null && typeof value === 'object'
          ? JSON.stringify(value)
          : String(value)
      return `${key.replace(/_/g, ' ')}: ${shown}`
    })
    .join(' · ')
}

// ---------- errors ----------

const MESSAGES = {
  cannot_deactivate_self: "You can't deactivate your own account.",
  cannot_reset_own_totp: 'To reset your own 2FA, ask another admin or use the server command.',
  use_change_password: 'Change your own password on the Security page.',
  cannot_deactivate_own_tech: "You can't deactivate the tech your own login is linked to.",
  not_found: 'That record no longer exists. Reload and try again.',
  retention_expired: 'This record is past the retention period and can no longer be restored.',
  client_deleted: 'Restore the client first.',
  csrf_failed: 'Your session needs refreshing. Reload the page and try again.',
}

export function adminErrorMessage(err) {
  return MESSAGES[err?.code] ?? err?.message ?? 'Something went wrong.'
}

// ---------- the admin page ----------

export const ADMIN_TABS = [
  { key: 'users', label: 'Users', roles: ['admin'] },
  { key: 'techs', label: 'Techs', roles: ['admin'] },
  { key: 'locations', label: 'Locations', roles: ['admin'] },
  { key: 'restore', label: 'Restore', roles: ['admin'] },
  { key: 'audit', label: 'Audit log', roles: ['admin', 'manager'] },
]

export const adminTabsFor = (role) => ADMIN_TABS.filter((t) => t.roles.includes(role))

/** The tab to show: the one asked for if this role may see it, else the first one it may see. */
export function resolveAdminTab(role, requested) {
  const tabs = adminTabsFor(role)
  if (!tabs.length) return null
  return tabs.find((t) => t.key === requested)?.key ?? tabs[0].key
}