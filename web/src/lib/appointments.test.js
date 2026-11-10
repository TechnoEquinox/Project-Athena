import { describe, expect, it } from 'vitest'
import {
  buildAppointmentPayload, deviceOptions, emptyAppointmentForm, locationOptions,
  rangeToParams, techOptions, toApiTime, yearRange,
} from './appointments'

// Local-time dates, so the tests don't depend on the machine's time zone
const NOW = new Date(2026, 10, 10, 13, 45, 0)

const appt = {
  appointment_id: 7,
  appointment_at: '2026-01-15T19:30:00+00:00',
  length_minutes: 45,
  client: { client_id: 5, first_name: 'Ada', last_name: 'Lovelace' },
  tech: { tech_id: 2, first_name: 'Pat', last_name: 'Lee' },
  location: { location_id: 3, name: 'Library' },
  notes: 'Fixed email',
  devices: [{ device_id: 11, removed: false }, { device_id: 12, removed: true }],
}

describe('yearRange', () => {
  it('runs from January 1 to December 31 of the current year', () => {
    const [start, end] = yearRange(NOW)
    expect(start).toEqual(new Date(2026, 0, 1))
    expect(end).toEqual(new Date(2026, 11, 31))
  })
})

describe('rangeToParams', () => {
  it('includes the whole last day by ending at the start of the next one', () => {
    expect(rangeToParams([new Date(2026, 0, 1), new Date(2026, 11, 31)])).toEqual({
      from: new Date(2026, 0, 1).toISOString(),
      to: new Date(2027, 0, 1).toISOString(),
    })
  })

  it('ignores the time of day on the picked dates', () => {
    expect(rangeToParams([new Date(2026, 5, 3, 15, 30), new Date(2026, 5, 4, 9, 0)])).toEqual({
      from: new Date(2026, 5, 3).toISOString(),
      to: new Date(2026, 5, 5).toISOString(),
    })
  })

  it('treats a single picked day as that whole day', () => {
    expect(rangeToParams([new Date(2026, 5, 3), null])).toEqual({
      from: new Date(2026, 5, 3).toISOString(),
      to: new Date(2026, 5, 4).toISOString(),
    })
  })

  it('sends nothing without a range', () => {
    expect(rangeToParams(null)).toEqual({})
    expect(rangeToParams([])).toEqual({})
  })
})

describe('toApiTime', () => {
  it('sends an exact instant in UTC', () => {
    expect(toApiTime(new Date('2026-01-15T14:30:00-05:00'))).toBe('2026-01-15T19:30:00.000Z')
  })
})

describe('emptyAppointmentForm', () => {
  it('starts blank for a new appointment, set to now', () => {
    expect(emptyAppointmentForm(null, { now: NOW })).toEqual({
      client: null, when: NOW, location_id: null, length_minutes: null,
      notes: '', device_ids: [], tech_id: null,
    })
  })

  it('prefills the client and the default tech', () => {
    const client = { client_id: 5, label: 'Lovelace, Ada' }
    const form = emptyAppointmentForm(null, { now: NOW, client, techId: 2 })
    expect(form.client).toEqual(client)
    expect(form.tech_id).toBe(2)
  })

  it('prefills from an existing appointment', () => {
    expect(emptyAppointmentForm(appt)).toEqual({
      client: { client_id: 5, label: 'Lovelace, Ada' },
      when: new Date('2026-01-15T19:30:00+00:00'),
      location_id: 3, length_minutes: 45, notes: 'Fixed email', device_ids: [11, 12], tech_id: 2,
    })
  })
})

describe('buildAppointmentPayload', () => {
  const filled = () => ({
    client: { client_id: 5, label: 'Lovelace, Ada' },
    when: new Date('2026-01-15T14:30:00-05:00'),
    location_id: 3, length_minutes: 45, notes: '', device_ids: [], tech_id: 2,
  })
  const edit = (changes, options) =>
    buildAppointmentPayload({ ...emptyAppointmentForm(appt), ...changes }, appt, options)

  it('creates with the required fields only', () => {
    expect(buildAppointmentPayload(filled())).toEqual({
      client_id: 5, appointment_at: '2026-01-15T19:30:00.000Z', location_id: 3, length_minutes: 45,
    })
  })

  it('adds trimmed notes and sorted devices when filled in', () => {
    const payload = buildAppointmentPayload({ ...filled(), notes: ' Fixed email ', device_ids: [12, 11] })
    expect(payload.notes).toBe('Fixed email')
    expect(payload.device_ids).toEqual([11, 12])
  })

  it('sends the tech only when asked to, which is for admins', () => {
    expect(buildAppointmentPayload(filled(), null, { sendTech: true })).toMatchObject({ tech_id: 2 })
    expect(buildAppointmentPayload(filled())).not.toHaveProperty('tech_id')
  })

  it('sends nothing when an edit changes nothing', () => {
    expect(edit({})).toEqual({})
  })

  it('sends only the fields that changed', () => {
    expect(edit({ length_minutes: 60, location_id: 4 })).toEqual({ length_minutes: 60, location_id: 4 })
  })

  it('sends a changed time', () => {
    expect(edit({ when: new Date('2026-01-15T20:00:00+00:00') })).toEqual({
      appointment_at: '2026-01-15T20:00:00.000Z',
    })
  })

  it('clears notes with null', () => {
    expect(edit({ notes: '   ' })).toEqual({ notes: null })
  })

  it('does not clear notes that were already empty', () => {
    const empty = { ...appt, notes: null }
    expect(buildAppointmentPayload(emptyAppointmentForm(empty), empty)).toEqual({})
  })

  it('sends devices only when the set changes, ignoring order', () => {
    expect(edit({ device_ids: [12, 11] })).toEqual({})
    expect(edit({ device_ids: [11] })).toEqual({ device_ids: [11] })
    expect(edit({ device_ids: [] })).toEqual({ device_ids: [] })
  })

  it('sends a tech change only for admins', () => {
    expect(edit({ tech_id: 9 })).toEqual({})
    expect(edit({ tech_id: 9 }, { sendTech: true })).toEqual({ tech_id: 9 })
    expect(edit({}, { sendTech: true })).toEqual({})
  })
})

describe('deviceOptions', () => {
  const devices = [
    { device_id: 11, device_type: 'Phone', description: 'iPhone 13' },
    { device_id: 13, device_type: 'Tablet', description: null },
  ]

  it("labels the client's devices", () => {
    expect(deviceOptions(devices)).toEqual([
      { device_id: 11, label: 'Phone: iPhone 13' },
      { device_id: 13, label: 'Tablet' },
    ])
  })

  it('keeps a removed device that is already linked, marked as removed', () => {
    const linked = [{ device_id: 12, device_type: 'Laptop', description: 'old', removed: true }]
    expect(deviceOptions(devices, linked)).toEqual([
      { device_id: 11, label: 'Phone: iPhone 13' },
      { device_id: 12, label: 'Laptop: old (removed)' },
      { device_id: 13, label: 'Tablet' },
    ])
  })
})

describe('locationOptions', () => {
  const active = [
    { location_id: 1, name: 'Library', is_active: true },
    { location_id: 2, name: 'Senior Center', is_active: true },
  ]
  const plain = [{ location_id: 1, name: 'Library' }, { location_id: 2, name: 'Senior Center' }]

  it('lists the active locations', () => {
    expect(locationOptions(active)).toEqual(plain)
  })

  it("keeps the appointment's own location even if it was removed", () => {
    expect(locationOptions(active, { location_id: 3, name: 'Outreach' })).toEqual([
      ...plain, { location_id: 3, name: 'Outreach (no longer in use)' },
    ])
  })

  it('does not repeat a current location that is still active', () => {
    expect(locationOptions(active, { location_id: 1, name: 'Library' })).toEqual(plain)
  })
})

describe('techOptions', () => {
  it('labels techs by last name, then first name', () => {
    expect(techOptions([{ tech_id: 1, first_name: 'Pat', last_name: 'Lee' }])).toEqual([
      { tech_id: 1, label: 'Lee, Pat' },
    ])
  })

  it("keeps the appointment's tech even if they are inactive", () => {
    const current = { tech_id: 9, first_name: 'Old', last_name: 'Timer' }
    expect(techOptions([{ tech_id: 1, first_name: 'Pat', last_name: 'Lee' }], current)).toEqual([
      { tech_id: 1, label: 'Lee, Pat' },
      { tech_id: 9, label: 'Timer, Old (inactive)' },
    ])
  })
})