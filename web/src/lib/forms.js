// Capitalised on purpose: the dashboard counts devices by this exact text.
export const DEVICE_TYPES = [
  'Phone', 'Tablet', 'Laptop', 'Desktop', 'Smartwatch', 'Smart TV', 'E-reader', 'Other',
]

// Capitalised on purpose: the server stores the text exactly as sent.
export const LANGUAGES = [
  'English', 'Spanish', 'Portuguese', 'Italian', 'Polish', 'French', 'Haitian Creole',
  'Russian', 'Ukrainian', 'Albanian', 'Arabic', 'Chinese (Mandarin)', 'Chinese (Cantonese)',
  'Hindi', 'Gujarati', 'Korean', 'Vietnamese', 'American Sign Language', 'Other',
]
export const MAX_LANGUAGES = 10   // the API's limit

function canonicalLanguage(name) {
  return LANGUAGES.find((l) => l.toLowerCase() === name.toLowerCase()) ?? name
}

/** Standard spellings, no repeats, standard list order first, then anything else alphabetically. */
export function orderLanguages(list) {
  const seen = new Set()
  const out = []
  for (const item of list ?? []) {
    const name = canonicalLanguage(String(item).trim())
    if (!name || seen.has(name.toLowerCase())) continue
    seen.add(name.toLowerCase())
    out.push(name)
  }
  const rank = (name) => {
    const i = LANGUAGES.indexOf(name)
    return i === -1 ? LANGUAGES.length : i
  }
  return out.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
}

/** The standard list, plus any language the client already has that isn't on it. */
export function languageOptions(current = []) {
  const known = new Set(LANGUAGES.map((l) => l.toLowerCase()))
  const extras = orderLanguages(current).filter((l) => !known.has(l.toLowerCase()))
  return [...LANGUAGES, ...extras]
}

function sameLanguages(a, b) {
  const key = (list) => JSON.stringify(orderLanguages(list).map((l) => l.toLowerCase()))
  return key(a) === key(b)
}

export function digitsOf(value) {
  return String(value ?? '').replace(/\D/g, '')
}

export function formatPhone(value) {
  if (!value) return ''
  const text = String(value)
  const m = /^(\d{3})(\d{3})(\d{4})$/.exec(text)
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : text
}

export function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString() : ''
}

export function emptyClientForm(client = null) {
  return {
    first_name: client?.first_name ?? '',
    last_name: client?.last_name ?? '',
    phone: client?.phone ? formatPhone(client.phone) : '',
    email: client?.email ?? '',
    zipcode: client?.zipcode ?? '',
    languages: orderLanguages(client?.languages),
  }
}

/**
 * Turn the form into an API body.
 * Create: names plus whatever optional fields are filled in.
 * Edit: only the fields that actually changed. Blank optional fields become null (cleared).
 */
export function buildClientPayload(form, original = null) {
  const next = {
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    phone: form.phone.trim(),
    email: form.email.trim(),
    zipcode: form.zipcode.trim(),
    languages: orderLanguages(form.languages),
  }

  if (!original) {
    const out = { first_name: next.first_name, last_name: next.last_name }
    for (const key of ['phone', 'email', 'zipcode']) {
      if (next[key]) out[key] = next[key]
    }
    if (next.languages.length) out.languages = next.languages
    return out
  }

  const out = {}
  if (next.first_name !== original.first_name) out.first_name = next.first_name
  if (next.last_name !== original.last_name) out.last_name = next.last_name
  const unusablePhone = next.phone !== '' && digitsOf(next.phone) === ''
  if (digitsOf(next.phone) !== digitsOf(original.phone) || unusablePhone) {
    out.phone = next.phone || null
  }
  if (next.email.toLowerCase() !== (original.email ?? '')) out.email = next.email || null
  if (next.zipcode !== (original.zipcode ?? '')) out.zipcode = next.zipcode || null
  if (!sameLanguages(next.languages, original.languages)) out.languages = next.languages
  return out
}

export function emptyDeviceForm(device = null) {
  return { device_type: device?.device_type ?? '', description: device?.description ?? '' }
}

export function buildDevicePayload(form, original = null) {
  const type = (form.device_type ?? '').trim()
  const description = (form.description ?? '').trim()
  if (!original) {
    const out = { device_type: type }
    if (description) out.description = description
    return out
  }
  const out = {}
  if (type !== original.device_type) out.device_type = type
  if (description !== (original.description ?? '')) out.description = description || null
  return out
}

/** The standard list, plus the device's current type if it isn't one of them. */
export function deviceTypeOptions(current = null) {
  return current && !DEVICE_TYPES.includes(current) ? [...DEVICE_TYPES, current] : [...DEVICE_TYPES]
}

/** Pull { field, message } out of a server validation error, or null for anything else. */
export function fieldErrorFrom(err) {
  if (err?.code === 'validation_failed' && err.body?.field) {
    return { field: err.body.field, message: err.body.message ?? 'That value is not valid.' }
  }
  return null
}