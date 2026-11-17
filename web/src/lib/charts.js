// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { roleLabel } from './admin'

// Colour-blind-friendly palette. Wraps around if there are more series than colours.
export const PALETTE = [
  '#0072B2', '#E69F00', '#009E73', '#D55E00', '#CC79A7',
  '#56B4E9', '#999999', '#882255', '#44AA99', '#DDCC77',
]
export const colorAt = (i) => PALETTE[i % PALETTE.length]

/** A navigator's name for a legend. Two people with the same name are told apart by role, or by id. */
export function techChartLabel(tech, all) {
  const full = `${tech.first_name} ${tech.last_name}`
  const same = all.filter((t) => `${t.first_name} ${t.last_name}` === full)
  if (same.length < 2) return full
  const roles = same.map((t) => t.login_role)
  const distinct = roles.every(Boolean) && new Set(roles).size === roles.length
  return distinct ? `${full} - ${roleLabel(tech.login_role)}` : `${full} (#${tech.tech_id})`
}

const labelsOf = (report) => report.buckets.map((b) => b.label)

const bars = (label, data, i) => ({ label, data, backgroundColor: colorAt(i) })
const line = (label, data, i) => ({
  label, data, borderColor: colorAt(i), backgroundColor: colorAt(i), tension: 0.2, spanGaps: false,
})

export function appointmentsChart(report, mode) {
  const labels = labelsOf(report)
  if (mode === 'tech') {
    return {
      labels,
      datasets: report.techs.map((t, i) => bars(techChartLabel(t, report.techs), t.counts, i)),
    }
  }
  return { labels, datasets: [bars('Appointments', report.total.counts, 0)] }
}

export function paceChart(report, mode) {
  const labels = labelsOf(report)
  if (mode === 'tech') {
    return {
      labels,
      datasets: report.techs.map((t, i) => line(techChartLabel(t, report.techs), t.average_minutes, i)),
    }
  }
  return { labels, datasets: [line('Average minutes', report.total.average_minutes, 0)] }
}

export function callsChart(report, direction, mode) {
  const labels = labelsOf(report)
  if (mode === 'tech') {
    return {
      labels,
      datasets: report.techs.map((t, i) => bars(techChartLabel(t, report.techs), t[direction], i)),
    }
  }
  const name = direction === 'inbound' ? 'Inbound calls' : 'Outbound calls'
  return { labels, datasets: [bars(name, report.total[direction], direction === 'inbound' ? 0 : 1)] }
}

export function locationsChart(report) {
  return {
    labels: labelsOf(report),
    datasets: report.locations.map((l, i) =>
      line(l.is_active === false ? `${l.name} (inactive)` : l.name, l.counts, i),
    ),
  }
}

export function devicesChart(report) {
  return {
    labels: report.devices.map((d) => d.device_type),
    datasets: [{
      data: report.devices.map((d) => d.count),
      backgroundColor: report.devices.map((_, i) => colorAt(i)),
    }],
  }
}

export const appointmentsEmpty = (report) => !report || report.total.count === 0
export const callsEmpty = (report) =>
  !report || report.total.inbound_count + report.total.outbound_count === 0
export const locationsEmpty = (report) => !report || report.locations.length === 0
export const devicesEmpty = (report) => !report || report.devices.length === 0

export const appointmentRows = (report) =>
  report.techs.map((t) => ({
    tech_id: t.tech_id,
    name: techChartLabel(t, report.techs),
    count: t.count,
    average: t.overall_average_minutes,
  }))

export const callRows = (report) =>
  report.techs.map((t) => ({
    tech_id: t.tech_id,
    name: techChartLabel(t, report.techs),
    inbound: t.inbound_count,
    outbound: t.outbound_count,
  }))

export const formatMinutes = (value) => (value == null ? '—' : `${value} min`)

export function axisOptions({ legend = false, integer = false, yTitle = '' } = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: legend, position: 'bottom' } },
    scales: {
      y: {
        beginAtZero: true,
        ticks: integer ? { precision: 0 } : {},
        title: { display: !!yTitle, text: yTitle },
      },
    },
  }
}

export const pieOptions = () => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: 'right' } },
})

// ---------- languages spoken ----------

const TOP_LANGUAGES = 12

export function topLanguages(report, limit = TOP_LANGUAGES) {
  return {
    shown: report.languages.slice(0, limit),
    hidden: Math.max(0, report.languages.length - limit),
  }
}

export function languagesChart(report, limit = TOP_LANGUAGES) {
  const { shown } = topLanguages(report, limit)
  return {
    labels: shown.map((l) => l.language),
    datasets: [{ label: 'Clients', data: shown.map((l) => l.clients), backgroundColor: colorAt(0) }],
  }
}

export const languagesEmpty = (report) => !report || report.languages.length === 0

export function languageSummary(report) {
  const total = report.total_clients
  return {
    total,
    multilingual: report.multilingual_clients,
    noLanguage: report.no_language,
    multilingualPct: total ? Math.round((100 * report.multilingual_clients) / total) : 0,
  }
}

/** Chart height in rem: tall enough for the bars to be readable, with a floor and a ceiling. */
export const languagesHeight = (bars) => Math.min(40, Math.max(12, 3 + bars * 1.7))

export const languagesOptions = () => ({
  responsive: true,
  maintainAspectRatio: false,
  indexAxis: 'y',
  plugins: { legend: { display: false } },
  scales: {
    x: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: 'Clients' } },
    y: { ticks: { autoSkip: false } },
  },
})