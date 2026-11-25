// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { formatPhone } from './forms'

export const WEEKDAYS = [
  { value: 0, label: 'Monday' }, { value: 1, label: 'Tuesday' }, { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' }, { value: 4, label: 'Friday' }, { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' },
]

export const DEFAULT_COLORS = ['#2563eb', '#16a34a', '#d97706', '#9333ea', '#dc2626', '#0891b2', '#be185d', '#4d7c0f']

export const STATUS_LABELS = {
  scheduled: 'Scheduled', completed: 'Completed', no_show: 'No-show', cancelled: 'Cancelled',
}

const pad = (n) => String(n).padStart(2, '0')

/** YYYY-MM-DD from the LOCAL date fields. toISOString() would shift the day for evening times. */
export function toLocalISODate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export const formatSlot = (iso) =>
  new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

export const formatBookingTime = (iso) =>
  new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })

export const navigatorName = (t) => `${t.first_name} ${t.last_name}`

export function colorMap(navigators) {
  return Object.fromEntries(navigators.map((n) => [n.tech_id, n.color]))
}

/** Cancelled bookings stay visible but muted. The navigator's name is in the title so color is never the only cue. */
export function toCalendarEvents(bookings, colors) {
  return bookings.map((b) => {
    const color = colors[b.tech.tech_id] ?? '#64748b'
    return {
      id: String(b.booking_id),
      title: `${b.client.first_name} ${b.client.last_name} · ${b.tech.first_name}`,
      start: b.starts_at,
      end: b.ends_at,
      backgroundColor: color,
      borderColor: color,
      classNames: b.status === 'scheduled' ? [] : [`booking-${b.status}`],
      extendedProps: { status: b.status, techId: b.tech.tech_id },
    }
  })
}

export function contactRows(client) {
  return [
    { label: 'Phone', value: client.phone ? formatPhone(client.phone) : '' },
    { label: 'Email', value: client.email ?? '' },
    { label: 'Language', value: (client.languages ?? []).join(', ') },
  ].map((r) => ({ ...r, value: r.value || 'Not on file' }))
}

// ---------- the availability form ----------

export const CYCLE_OPTIONS = [
  { label: 'Every week', value: 1 },
  { label: 'Alternating weeks', value: 2 },
]

/** The Monday of the week containing `d`, at local midnight. */
export function mondayOf(d) {
  const monday = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7))
  return monday
}

/** 'YYYY-MM-DD' to a local Date. new Date('2030-01-07') would be UTC and can land on the day before. */
export function parseLocalDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** Which week of the cycle `day` is in: 1 or 2. Same rule as the server (Monday-based, counts backwards too). */
export function cycleWeekNumber(day, cycleStart, cycleWeeks) {
  if (cycleWeeks <= 1 || !cycleStart) return 1
  const days = Math.round((mondayOf(day) - mondayOf(cycleStart)) / 86400000)
  const weeks = Math.floor(days / 7)
  return (((weeks % cycleWeeks) + cycleWeeks) % cycleWeeks) + 1
}

export function buildDays(windows = [], week=0) {
  return WEEKDAYS.map(({ value, label }) => {
    const blocks = windows
      .filter((w) => (w.week ?? 0) === week && w.weekday === value)
      .map((w) => ({ start: w.start_time, end: w.end_time }))
    return { weekday: value, label, enabled: blocks.length > 0, blocks }
  })
}

export function buildWindows(weeks, cycleWeeks = 1) {
  return weeks.slice(0, cycleWeeks).flatMap((days, week) =>
    days.filter((d) => d.enabled).flatMap((d) =>
      d.blocks.map((b) => ({ week, weekday: d.weekday, start_time: b.start, end_time: b.end })),    
    ),
  )
}

/** The same rules the server enforces, so the admin sees the problem before saving. */
export function availabilityProblem(form) {
  const minutes = form.appointment_minutes
  if (!Number.isInteger(minutes) || minutes < 5 || minutes > 240) return 'Appointment length must be 5 to 240 minutes.'
  const buffer = form.buffer_minutes
  if (!Number.isInteger(buffer) || buffer < 0 || buffer > 120) return 'Down-time must be 0 to 120 minutes.'
  if (!/^#[0-9a-fA-F]{6}$/.test(form.color ?? '')) return 'Pick a calendar color.'
  if (form.cycle_weeks === 2 && !(form.cycle_start instanceof Date)) return 'Pick the date Week 1 starts on.'
  
  for (const [index, days] of form.weeks.slice(0, form.cycle_weeks).entries()) {
    const prefix = form.cycle_weeks === 2 ? `Week ${index + 1}, ` : ''
    
    for (const day of days.filter((d) => d.enabled)) {
      if (!day.blocks.length) return `${prefix}${day.label}: add a time block, or turn the day off.`
      
      const sorted = [...day.blocks].sort((a, b) => a.start.localeCompare(b.start))
      
      for (const [i, b] of sorted.entries()) {
        if (!b.start || !b.end || b.start >= b.end) return `${prefix}${day.label}: each block must end after it starts.`
        if (i > 0 && b.start < sorted[i - 1].end) return `${prefix}${day.label}: blocks can't overlap.`
      }
    }
  }
  return ''
}

export function buildAvailabilityPayload(form) {
  const payload = {
    appointment_minutes: form.appointment_minutes,
    buffer_minutes: form.buffer_minutes,
    color: form.color,
    cycle_weeks: form.cycle_weeks,
    windows: buildWindows(form.weeks, form.cycle_weeks),
  }
  if (form.cycle_weeks === 2) payload.cycle_start = toLocalISODate(form.cycle_start)
  return payload
}

export function formFromAvailability(row, fallbackColor = DEFAULT_COLORS[0]) {
  const windows = row.windows ?? []
  return {
    appointment_minutes: row.appointment_minutes ?? 30,
    buffer_minutes: row.buffer_minutes ?? 0,
    color: row.color ?? fallbackColor,
    cycle_weeks: row.cycle_weeks ?? 1,
    cycle_start: row.cycle_start ? parseLocalDate(row.cycle_start) : null,
    weeks: [buildDays(windows, 0), buildDays(windows, 1)],
  }
}

const dayNames = (windows, week) =>
  [...new Set(windows.filter((w) => (w.week ?? 0) === week).map((w) => w.weekday))]
    .sort((a, b) => a - b)
    .map((d) => WEEKDAYS[d].label.slice(0, 3))
    .join(', ')

export function summarize(row) {
  if (!row.configured) return 'Not set up'
  const base = `${row.appointment_minutes} min · ${row.buffer_minutes} min down-time`
  if ((row.cycle_weeks ?? 1) === 2) {
    return `${base} · Week 1: ${dayNames(row.windows, 0) || 'none'}; Week 2: ${dayNames(row.windows, 1) || 'none'}`
  }
  return `${base} · ${dayNames(row.windows, 0) || 'no days'}`
}

// ---------- time off (blocked days) ----------

/** Add days to a YYYY-MM-DD date and return YYYY-MM-DD (local calendar maths, so daylight saving can't shift it). */
export function addDaysISO(iso, n) {
  const d = parseLocalDate(iso)
  d.setDate(d.getDate() + n)
  return toLocalISODate(d)
}

export function formatDateRange(start, end) {
  const fmt = (iso) => parseLocalDate(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
  return start === end ? fmt(start) : `${fmt(start)} to ${fmt(end)}`
}

/** "Everyone", or the names of the navigators a block applies to. */
export function timeOffWho(block, navigators) {
  if (block.all_navigators) return 'All navigators'
  const byId = Object.fromEntries(navigators.map((n) => [n.tech_id, navigatorName(n)]))
  return block.tech_ids.map((id) => byId[id] ?? `Navigator ${id}`).join(', ')
}

/** Each block becomes a labelled all-day bar plus a light shading of its days. FullCalendar's end date is exclusive. */
export function timeOffEvents(blocks, navigators) {
  return blocks.flatMap((b) => {
    const end = addDaysISO(b.end_date, 1)
    const who = b.all_navigators ? '' : ` (${timeOffWho(b, navigators)})`
    return [
      {
        id: `off-${b.time_off_id}`, title: `Closed: ${b.description}${who}`, start: b.start_date, end, allDay: true,
        backgroundColor: '#e5e7eb', borderColor: '#9ca3af', textColor: '#374151',
        classNames: ['time-off'], editable: false, extendedProps: { kind: 'time_off' },
      },
      {
        id: `off-bg-${b.time_off_id}`, start: b.start_date, end, allDay: true, display: 'background',
        classNames: ['time-off-bg'], extendedProps: { kind: 'time_off' },
      },
    ]
  })
}

export function emptyTimeOffForm() {
  return { dates: null, all: true, tech_ids: [], description: '' }
}

export function formFromTimeOff(block) {
  const start = parseLocalDate(block.start_date)
  const end = parseLocalDate(block.end_date)
  return {
    dates: [start, block.end_date === block.start_date ? null : end],
    all: block.all_navigators,
    tech_ids: [...block.tech_ids],
    description: block.description,
  }
}

/** The same rules the server enforces. */
export function timeOffProblem(form) {
  if (!Array.isArray(form.dates) || !(form.dates[0] instanceof Date)) return 'Pick a day, or a first and last day.'
  const [start, end] = form.dates
  if (end && end < start) return "The last day can't be before the first day."
  if (end && (end - start) / 86400000 > 365) return 'A block can cover at most one year.'
  if (!form.description.trim()) return 'Add a short description, like Christmas.'
  if (form.description.trim().length > 200) return 'The description must be at most 200 characters.'
  if (!form.all && !form.tech_ids.length) return 'Pick at least one navigator, or choose all navigators.'
  return ''
}

export function buildTimeOffPayload(form) {
  const [start, end] = form.dates
  return {
    start_date: toLocalISODate(start),
    end_date: toLocalISODate(end ?? start),   // a single day when no second date was picked
    description: form.description.trim(),
    all_navigators: form.all,
    tech_ids: form.all ? [] : form.tech_ids,
  }
}

export function affectedMessage(count) {
  if (!count) return ''
  const noun = count === 1 ? 'appointment is' : 'appointments are'
  return `${count} booked ${noun} already on these days. Nothing was changed; move or cancel them from the calendar.`
}

const MESSAGES = {
  slot_unavailable: 'That time was just taken. Pick another.',
  not_configured: "This navigator's availability hasn't been set up yet.",
  forbidden: "You can only change your own bookings.",
  forbidden_field: 'You can only book for yourself.',
}

export function schedulingErrorMessage(err) {
  return MESSAGES[err?.code] ?? err?.message ?? 'Something went wrong.'
}