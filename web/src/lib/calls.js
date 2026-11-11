import { clientLabel, toApiTime } from './appointments'
import { digitsOf, formatPhone } from './forms'

export const OPEN_STATUSES = ['needs_call', 'needs_email', 'needs_attention']
export const DONE_STATUS = 'no_action_required'

const SEVERITY = {
  needs_call: 'warn',
  needs_email: 'info',
  needs_attention: 'danger',
  no_action_required: 'success',
  outgoing: 'secondary',
}

export const statusSeverity = (status) => SEVERITY[status] ?? 'secondary'
export const isOpen = (status) => OPEN_STATUSES.includes(status)

export function callerName(call) {
  const typed = [call.client_first_name, call.client_last_name].filter(Boolean).join(' ')
  if (typed) return typed
  if (call.client) return `${call.client.first_name} ${call.client.last_name}`
  return 'Unknown caller'
}

const plural = (n, unit) => `${n} ${unit}${n === 1 ? '' : 's'}`

/** How long a call has been waiting, e.g. "2 days". */
export function waitingFor(iso, now = new Date()) {
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 60000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return plural(minutes, 'minute')
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return plural(hours, 'hour')
  return plural(Math.floor(hours / 24), 'day')
}

/** A call has to say who it was: a linked client, a name, or a phone number. */
export function hasCaller(form) {
  return Boolean(
    form.client || form.first_name.trim() || form.last_name.trim() || digitsOf(form.phone),
  )
}

export function emptyCallForm(call = null, { now = new Date(), techId = null, client = null } = {}) {
  if (call) {
    return {
      status: call.status,
      when: new Date(call.called_at),
      first_name: call.client_first_name ?? '',
      last_name: call.client_last_name ?? '',
      phone: call.phone ? formatPhone(call.phone) : '',
      notes: call.notes ?? '',
      client: call.client
        ? { client_id: call.client.client_id, label: clientLabel(call.client) }
        : null,
      tech_id: call.tech?.tech_id ?? null,
    }
  }
  return {
    status: null, when: new Date(now), first_name: '', last_name: '', phone: '', notes: '',
    client, tech_id: techId,
  }
}

/**
 * Create: the status, plus whatever is filled in. The time is left out while it is still the
 * default of "now", so the server stamps it.
 * Edit: only the fields that changed. Blank optional fields become null.
 * The tech is sent only when sendTech is true.
 */
export function buildCallPayload(form, original = null, { sendTech = false, defaultWhen = null } = {}) {
  const first = form.first_name.trim()
  const last = form.last_name.trim()
  const phone = form.phone.trim()
  const notes = form.notes.trim()

  if (!original) {
    const out = { status: form.status }
    if (!(defaultWhen && form.when.getTime() === defaultWhen.getTime())) {
      out.called_at = toApiTime(form.when)
    }
    if (first) out.client_first_name = first
    if (last) out.client_last_name = last
    if (phone) out.phone = phone
    if (notes) out.notes = notes
    if (form.client) out.client_id = form.client.client_id
    if (sendTech && form.tech_id != null) out.tech_id = form.tech_id
    return out
  }

  const out = {}
  if (form.status !== original.status) out.status = form.status
  if (form.when.getTime() !== new Date(original.called_at).getTime()) {
    out.called_at = toApiTime(form.when)
  }
  if (first !== (original.client_first_name ?? '')) out.client_first_name = first || null
  if (last !== (original.client_last_name ?? '')) out.client_last_name = last || null
  const unusablePhone = phone !== '' && digitsOf(phone) === ''
  if (digitsOf(phone) !== digitsOf(original.phone) || unusablePhone) out.phone = phone || null
  if ((notes || null) !== (original.notes ?? null)) out.notes = notes || null
  const clientId = form.client?.client_id ?? null
  if (clientId !== (original.client?.client_id ?? null)) out.client_id = clientId
  if (sendTech && form.tech_id !== (original.tech?.tech_id ?? null)) out.tech_id = form.tech_id
  return out
}