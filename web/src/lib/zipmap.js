// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { geoBounds, geoMercator, geoPath } from 'd3-geo'

export const MAP_SIZE = { width: 800, height: 560 }
const PAD = 16
export const NEUTRAL = '#e5e7eb'
// ColorBrewer "Blues", light to dark
export const BLUES = ['#deebf7', '#9ecae1', '#6baed6', '#3182bd', '#08519c']

// When zooming to where clients live: a margin around them, and never tighter than this
// (about 25 km), so a single ZIP keeps its neighbours in view
const MARGIN = 0.15
const MIN_SPAN_LON = 0.3
const MIN_SPAN_LAT = 0.22

export const isConnecticutZip = (zip) => typeof zip === 'string' && /^06\d{3}$/.test(zip)

export function countsByZip(report) {
  return new Map(report.zips.map((z) => [z.zipcode, z.clients]))
}

/** Up to five shading steps covering 1..max, with no gaps and no empty steps. */
export function legendSteps(max) {
  if (!(max >= 1)) return []
  const classes = Math.min(BLUES.length, max)
  const size = Math.ceil(max / classes)
  const n = Math.ceil(max / size)
  return Array.from({ length: n }, (_, i) => ({
    from: i * size + 1,
    to: Math.min((i + 1) * size, max),
    color: n === 1 ? BLUES[3] : BLUES[Math.round((i * (BLUES.length - 1)) / (n - 1))],
  }))
}

export const stepLabel = (step) => (step.from === step.to ? `${step.from}` : `${step.from}–${step.to}`)

export function colorFor(count, steps) {
  if (!count || !steps.length) return NEUTRAL
  return (steps.find((s) => count >= s.from && count <= s.to) ?? steps[steps.length - 1]).color
}

/** [[west, south], [east, north]] around these features, with a margin and a minimum size. */
export function focusBox(features) {
  const [[w, s], [e, n]] = geoBounds({ type: 'FeatureCollection', features })
  const grow = (low, high, minSpan) => {
    const span = Math.max((high - low) * (1 + 2 * MARGIN), minSpan)
    const middle = (low + high) / 2
    return [middle - span / 2, middle + span / 2]
  }
  const [west, east] = grow(w, e, MIN_SPAN_LON)
  const [south, north] = grow(s, n, MIN_SPAN_LAT)
  return [[west, south], [east, north]]
}

/**
 * Everything needed to draw the map: one path per ZIP area.
 * mode 'focus' zooms to the ZIPs that have clients, 'state' shows all of Connecticut.
 */
export function buildMap(features, report, { mode = 'focus', width = MAP_SIZE.width, height = MAP_SIZE.height, pad = PAD } = {}) {
  const counts = countsByZip(report)
  const known = new Set(features.map((f) => f.properties.zip))
  const focus = features.filter((f) => (counts.get(f.properties.zip) ?? 0) > 0)

  // A MultiPoint of two corners fits exactly. A rectangle polygon would need the right winding.
  const target = mode === 'focus' && focus.length
    ? { type: 'MultiPoint', coordinates: focusBox(focus) }
    : { type: 'FeatureCollection', features }
  const projection = geoMercator().fitExtent([[pad, pad], [width - pad, height - pad]], target)
  const path = geoPath(projection)

  const maxCount = Math.max(0, ...focus.map((f) => counts.get(f.properties.zip)))
  const steps = legendSteps(maxCount)

  const paths = features
    .map((f) => {
      const count = counts.get(f.properties.zip) ?? 0
      return { zip: f.properties.zip, count, d: path(f) ?? '', color: colorFor(count, steps), center: path.centroid(f) }
    })
    .sort((a, b) => a.count - b.count)   // shaded areas last, so their outlines are on top

  const unmapped = report.zips.filter((z) => !known.has(z.zipcode))
  return {
    paths,
    steps,
    maxCount,
    unmapped,
    unmappedClients: unmapped.reduce((sum, z) => sum + z.clients, 0),
  }
}

export const tooltipText = (zip, clients) =>
  clients ? `${zip} · ${clients} client${clients === 1 ? '' : 's'}` : `${zip} · no clients`

export function summarize(report, unmappedClients = 0) {
  return {
    total: report.total_clients,
    connecticut: report.zips.reduce((sum, z) => sum + z.clients, 0),
    zipCount: report.zips.length,
    other: report.other,
    noZip: report.no_zip,
    unmapped: unmappedClients,
  }
}

export function zipRows(report) {
  const rows = report.zips.map((z) => ({ key: z.zipcode, label: z.zipcode, clients: z.clients }))
  if (report.other) rows.push({ key: 'other', label: 'Outside Connecticut', clients: report.other })
  if (report.no_zip) rows.push({ key: 'none', label: 'No ZIP recorded', clients: report.no_zip })
  return rows
}