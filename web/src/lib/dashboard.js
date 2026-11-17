// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const pad = (n) => String(n).padStart(2, '0')
const ymd = (y, m, d) => `${y}-${pad(m)}-${pad(d)}`
const lastDay = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate()   // m is 1-12
const parts = (text) => text.split('-').map(Number)

export const MAX_RANGE_DAYS = 3660   // the same limit as the server

export const INTERVAL_OPTIONS = [
  { label: 'Month', value: 'month' },
  { label: 'Quarter', value: 'quarter' },
  { label: 'Year', value: 'year' },
]

export const MODE_OPTIONS = [
  { label: 'All navigators', value: 'total' },
  { label: 'Per navigator', value: 'tech' },
]

export function formatDay(text) {
  const [y, m, d] = parts(text)
  return `${MONTHS[m - 1]} ${d}, ${y}`
}

const monthYear = (text) => {
  const [y, m] = parts(text)
  return `${MONTHS[m - 1]} ${y}`
}

export const rangeLabel = (from, to) => `${formatDay(from)} – ${formatDay(to)}`

function fiscalYear(y, m, start, offset) {
  const startYear = (m >= start ? y : y - 1) + offset
  const endMonth = start === 1 ? 12 : start - 1
  const endYear = start === 1 ? startYear : startYear + 1
  return { from: ymd(startYear, start, 1), to: ymd(endYear, endMonth, lastDay(endYear, endMonth)) }
}

/** The date range for a preset, given today's date (YYYY-MM-DD, in the library's time zone). */
export function presetRange(key, today, fiscalStartMonth = 7) {
  const [y, m] = parts(today)
  switch (key) {
    case 'thisMonth':
      return { from: ymd(y, m, 1), to: ymd(y, m, lastDay(y, m)) }
    case 'thisQuarter': {
      const first = 3 * Math.floor((m - 1) / 3) + 1
      return { from: ymd(y, first, 1), to: ymd(y, first + 2, lastDay(y, first + 2)) }
    }
    case 'thisYear':
      return { from: ymd(y, 1, 1), to: ymd(y, 12, 31) }
    case 'lastYear':
      return { from: ymd(y - 1, 1, 1), to: ymd(y - 1, 12, 31) }
    case 'fiscalYear':
      return fiscalYear(y, m, fiscalStartMonth, 0)
    case 'lastFiscalYear':
      return fiscalYear(y, m, fiscalStartMonth, -1)
    default:
      throw new Error(`Unknown preset: ${key}`)
  }
}

const PLAIN_LABELS = {
  thisMonth: 'This month', thisQuarter: 'This quarter', thisYear: 'This year', lastYear: 'Last year',
}
const FISCAL_LABELS = { fiscalYear: 'Fiscal year', lastFiscalYear: 'Last fiscal year' }

export function presetOptions(today, fiscalStartMonth = 7) {
  const keys = ['thisMonth', 'thisQuarter', 'thisYear', 'lastYear']
  if (fiscalStartMonth !== 1) keys.push('fiscalYear', 'lastFiscalYear')   // otherwise they repeat the calendar year
  return keys.map((key) => {
    const range = presetRange(key, today, fiscalStartMonth)
    const label = PLAIN_LABELS[key] ?? `${FISCAL_LABELS[key]} (${monthYear(range.from)} – ${monthYear(range.to)})`
    return { key, label, ...range }
  })
}

export const matchPreset = (from, to, options) =>
  options.find((o) => o.from === from && o.to === to)?.key ?? 'custom'

const daysBetween = (a, b) => Math.round((Date.UTC(...parts(b).map((n, i) => (i === 1 ? n - 1 : n))) - Date.UTC(...parts(a).map((n, i) => (i === 1 ? n - 1 : n)))) / 86400000)

/** What is wrong with a date range, or an empty string. */
export function rangeProblem(from, to) {
  if (!from || !to) return 'Pick a start and an end date.'
  if (from > to) return 'The start date must be on or before the end date.'
  if (daysBetween(from, to) >= MAX_RANGE_DAYS) return 'Choose a range of about ten years or less.'
  return ''
}

const TITLES = { month: 'This month', quarter: 'This quarter', year: 'This year' }

export function counterCards(data) {
  return Object.keys(TITLES).map((key) => {
    const counter = data?.counters?.[key]
    return {
      key,
      title: TITLES[key],
      period: counter?.label ?? '',
      value: counter ? counter.count.toLocaleString('en-US') : '—',
    }
  })
}