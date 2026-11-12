import { describe, expect, it } from 'vitest'
import {
  PALETTE, appointmentRows, appointmentsChart, appointmentsEmpty, axisOptions, callRows,
  callsChart, callsEmpty, colorAt, devicesChart, devicesEmpty, formatMinutes, locationsChart,
  locationsEmpty, paceChart, pieOptions, techChartLabel,
} from './charts'

const buckets = [
  { start: '2026-01-01', label: 'Jan 2026' },
  { start: '2026-02-01', label: 'Feb 2026' },
]
const pat = {
  tech_id: 1, first_name: 'Pat', last_name: 'Lee', login_role: 'navigator',
  counts: [1, 1], count: 2, average_minutes: [30, 60], overall_average_minutes: 45,
  inbound: [2, 0], outbound: [0, 1], inbound_count: 2, outbound_count: 1,
}
const sam = {
  tech_id: 2, first_name: 'Sam', last_name: 'Ray', login_role: null,
  counts: [0, 1], count: 1, average_minutes: [null, 45], overall_average_minutes: 45,
  inbound: [0, 0], outbound: [0, 3], inbound_count: 0, outbound_count: 3,
}
const appointments = {
  buckets,
  total: { counts: [1, 2], count: 3, average_minutes: [30, 52.5], overall_average_minutes: 45 },
  techs: [pat, sam],
}
const calls = {
  buckets,
  total: { inbound: [2, 0], outbound: [0, 4], inbound_count: 2, outbound_count: 4 },
  techs: [pat, sam],
}

describe('palette', () => {
  it('has distinct colours and wraps around', () => {
    expect(new Set(PALETTE).size).toBe(PALETTE.length)
    for (const color of PALETTE) expect(color).toMatch(/^#[0-9A-Fa-f]{6}$/)
    expect(colorAt(0)).toBe(PALETTE[0])
    expect(colorAt(PALETTE.length)).toBe(PALETTE[0])
    expect(colorAt(PALETTE.length + 1)).toBe(PALETTE[1])
  })
})

describe('techChartLabel', () => {
  const t = (id, first, last, role = null) => ({ tech_id: id, first_name: first, last_name: last, login_role: role })

  it('uses the plain name', () => {
    expect(techChartLabel(t(1, 'Pat', 'Lee'), [t(1, 'Pat', 'Lee'), t(2, 'Sam', 'Ray')])).toBe('Pat Lee')
  })
  it('tells apart two people with the same name by their roles', () => {
    const all = [t(1, 'Connor', 'Bailey', 'admin'), t(2, 'Connor', 'Bailey', 'navigator')]
    expect(all.map((x) => techChartLabel(x, all))).toEqual([
      'Connor Bailey - Admin', 'Connor Bailey - Navigator',
    ])
  })
  it('falls back to the id when roles do not tell them apart', () => {
    const same = [t(1, 'A', 'B', 'navigator'), t(2, 'A', 'B', 'navigator')]
    expect(same.map((x) => techChartLabel(x, same))).toEqual(['A B (#1)', 'A B (#2)'])
    const none = [t(1, 'A', 'B'), t(2, 'A', 'B', 'admin')]
    expect(none.map((x) => techChartLabel(x, none))).toEqual(['A B (#1)', 'A B (#2)'])
  })
})

describe('appointmentsChart', () => {
  it('shows one series for everyone', () => {
    const chart = appointmentsChart(appointments, 'total')
    expect(chart.labels).toEqual(['Jan 2026', 'Feb 2026'])
    expect(chart.datasets).toHaveLength(1)
    expect(chart.datasets[0]).toMatchObject({ label: 'Appointments', data: [1, 2] })
  })
  it('shows a series per navigator', () => {
    const chart = appointmentsChart(appointments, 'tech')
    expect(chart.datasets.map((d) => d.label)).toEqual(['Pat Lee', 'Sam Ray'])
    expect(chart.datasets.map((d) => d.data)).toEqual([[1, 1], [0, 1]])
    expect(chart.datasets[0].backgroundColor).toBe(PALETTE[0])
    expect(chart.datasets[1].backgroundColor).toBe(PALETTE[1])
  })
})

describe('paceChart', () => {
  it('draws the average length, leaving gaps where there were no appointments', () => {
    expect(paceChart(appointments, 'total').datasets[0]).toMatchObject({
      label: 'Average minutes', data: [30, 52.5], spanGaps: false,
    })
    const tech = paceChart(appointments, 'tech')
    expect(tech.datasets[1].data).toEqual([null, 45])
    expect(tech.datasets[1].borderColor).toBe(PALETTE[1])
  })
})

describe('callsChart', () => {
  it('draws one direction at a time', () => {
    expect(callsChart(calls, 'inbound', 'total').datasets[0]).toMatchObject({ label: 'Inbound calls', data: [2, 0] })
    expect(callsChart(calls, 'outbound', 'total').datasets[0]).toMatchObject({ label: 'Outbound calls', data: [0, 4] })
  })
  it('splits by navigator', () => {
    const chart = callsChart(calls, 'outbound', 'tech')
    expect(chart.datasets.map((d) => [d.label, d.data])).toEqual([['Pat Lee', [0, 1]], ['Sam Ray', [0, 3]]])
  })
})

describe('locationsChart', () => {
  const report = {
    buckets,
    locations: [
      { location_id: 1, name: 'Library', is_active: true, counts: [1, 1], count: 2 },
      { location_id: 3, name: 'Outreach', is_active: false, counts: [0, 1], count: 1 },
      { location_id: null, name: 'No location recorded', is_active: null, counts: [1, 0], count: 1 },
    ],
  }
  it('draws a line per location and marks removed ones', () => {
    const chart = locationsChart(report)
    expect(chart.labels).toEqual(['Jan 2026', 'Feb 2026'])
    expect(chart.datasets.map((d) => d.label)).toEqual([
      'Library', 'Outreach (inactive)', 'No location recorded',
    ])
    expect(chart.datasets[0]).toMatchObject({ data: [1, 1], borderColor: PALETTE[0] })
  })
})

describe('devicesChart', () => {
  it('draws a pie with a colour per type', () => {
    const chart = devicesChart({ devices: [{ device_type: 'Tablet', count: 2 }, { device_type: 'Phone', count: 1 }] })
    expect(chart.labels).toEqual(['Tablet', 'Phone'])
    expect(chart.datasets[0].data).toEqual([2, 1])
    expect(chart.datasets[0].backgroundColor).toEqual([PALETTE[0], PALETTE[1]])
  })
})

describe('empty checks', () => {
  it('knows when there is nothing to draw', () => {
    expect(appointmentsEmpty(null)).toBe(true)
    expect(appointmentsEmpty({ total: { count: 0 } })).toBe(true)
    expect(appointmentsEmpty(appointments)).toBe(false)
    expect(callsEmpty(null)).toBe(true)
    expect(callsEmpty({ total: { inbound_count: 0, outbound_count: 0 } })).toBe(true)
    expect(callsEmpty({ total: { inbound_count: 0, outbound_count: 1 } })).toBe(false)
    expect(locationsEmpty(null)).toBe(true)
    expect(locationsEmpty({ locations: [] })).toBe(true)
    expect(locationsEmpty({ locations: [{}] })).toBe(false)
    expect(devicesEmpty(null)).toBe(true)
    expect(devicesEmpty({ devices: [] })).toBe(true)
    expect(devicesEmpty({ devices: [{}] })).toBe(false)
  })
})

describe('totals tables', () => {
  it('lists each navigator with their numbers', () => {
    expect(appointmentRows(appointments)).toEqual([
      { tech_id: 1, name: 'Pat Lee', count: 2, average: 45 },
      { tech_id: 2, name: 'Sam Ray', count: 1, average: 45 },
    ])
    expect(callRows(calls)).toEqual([
      { tech_id: 1, name: 'Pat Lee', inbound: 2, outbound: 1 },
      { tech_id: 2, name: 'Sam Ray', inbound: 0, outbound: 3 },
    ])
  })
  it('formats minutes', () => {
    expect(formatMinutes(38.3)).toBe('38.3 min')
    expect(formatMinutes(null)).toBe('—')
  })
})

describe('chart options', () => {
  it('shows a legend only when asked', () => {
    expect(axisOptions().plugins.legend.display).toBe(false)
    expect(axisOptions({ legend: true }).plugins.legend.display).toBe(true)
  })
  it('keeps count axes to whole numbers, starting at zero', () => {
    const options = axisOptions({ integer: true })
    expect(options.scales.y.beginAtZero).toBe(true)
    expect(options.scales.y.ticks.precision).toBe(0)
    expect(axisOptions().scales.y.ticks.precision).toBeUndefined()
  })
  it('can title the vertical axis', () => {
    expect(axisOptions({ yTitle: 'Minutes' }).scales.y.title).toEqual({ display: true, text: 'Minutes' })
    expect(axisOptions().scales.y.title.display).toBe(false)
  })
  it('sizes to its container', () => {
    expect(axisOptions().maintainAspectRatio).toBe(false)
    expect(pieOptions().maintainAspectRatio).toBe(false)
  })
})