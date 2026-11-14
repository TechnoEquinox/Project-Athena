import { geoPath } from 'd3-geo'
import { describe, expect, it } from 'vitest'
import {
  BLUES, MAP_SIZE, NEUTRAL, buildMap, colorFor, countsByZip, focusBox, isConnecticutZip,
  legendSteps, stepLabel, summarize, tooltipText, zipRows,
} from './zipmap'

// Clockwise squares, the way d3 wants rings wound. Lon/lat near Cheshire and Wallingford.
const square = (zip, lon, lat, size = 0.05) => ({
  type: 'Feature',
  properties: { zip },
  geometry: {
    type: 'Polygon',
    coordinates: [[[lon, lat], [lon, lat + size], [lon + size, lat + size], [lon + size, lat], [lon, lat]]],
  },
})
const A = square('06410', -72.9, 41.5)
const B = square('06492', -72.85, 41.45)
const C = square('06001', -73.0, 41.9)   // about 0.4 degrees north
const FEATURES = [A, B, C]

const report = (zips, extra = {}) => ({
  zips,
  other: 0,
  no_zip: 0,
  total_clients: zips.reduce((sum, z) => sum + z.clients, 0),
  ...extra,
})
const zip = (zipcode, clients) => ({ zipcode, clients })
const find = (map, code) => map.paths.find((p) => p.zip === code)
const inside = ([x, y], w = MAP_SIZE.width, h = MAP_SIZE.height) => x >= 0 && x <= w && y >= 0 && y <= h

describe('isConnecticutZip', () => {
  it('accepts 06xxx and nothing else', () => {
    expect(isConnecticutZip('06410')).toBe(true)
    for (const bad of ['10001', '6410', '064100', '06A10', '', null, undefined]) {
      expect(isConnecticutZip(bad)).toBe(false)
    }
  })
})

describe('countsByZip', () => {
  it('maps each ZIP to its client count', () => {
    const counts = countsByZip(report([zip('06410', 3), zip('06492', 1)]))
    expect(counts.get('06410')).toBe(3)
    expect(counts.get('06492')).toBe(1)
    expect(counts.get('06001')).toBeUndefined()
  })
})

describe('legendSteps', () => {
  it('has no steps when nobody is shown', () => {
    expect(legendSteps(0)).toEqual([])
    expect(legendSteps(NaN)).toEqual([])
  })
  it('uses one dark step for a single client', () => {
    expect(legendSteps(1)).toEqual([{ from: 1, to: 1, color: BLUES[3] }])
  })
  it('uses a step per value when counts are small', () => {
    expect(legendSteps(3).map((s) => [s.from, s.to])).toEqual([[1, 1], [2, 2], [3, 3]])
  })
  it('drops empty steps', () => {
    expect(legendSteps(12).map((s) => [s.from, s.to])).toEqual([[1, 3], [4, 6], [7, 9], [10, 12]])
  })
  it('never exceeds five steps', () => {
    const steps = legendSteps(100)
    expect(steps).toHaveLength(5)
    expect(steps.map((s) => s.color)).toEqual(BLUES)
  })
  it.each([1, 2, 3, 5, 6, 12, 37, 100, 1234])('covers 1 to %i with no gaps', (max) => {
    const steps = legendSteps(max)
    expect(steps[0].from).toBe(1)
    expect(steps[steps.length - 1].to).toBe(max)
    steps.slice(1).forEach((s, i) => expect(s.from).toBe(steps[i].to + 1))
  })
  it('gets darker as counts rise', () => {
    const colors = legendSteps(40).map((s) => BLUES.indexOf(s.color))
    expect(colors).toEqual([...colors].sort((a, b) => a - b))
  })
  it('labels a step', () => {
    expect(stepLabel({ from: 1, to: 1 })).toBe('1')
    expect(stepLabel({ from: 4, to: 6 })).toBe('4–6')
  })
})

describe('colorFor', () => {
  const steps = legendSteps(12)
  it('leaves empty ZIPs neutral', () => {
    expect(colorFor(0, steps)).toBe(NEUTRAL)
    expect(colorFor(undefined, steps)).toBe(NEUTRAL)
  })
  it('picks the step that holds the count', () => {
    expect(colorFor(1, steps)).toBe(steps[0].color)
    expect(colorFor(3, steps)).toBe(steps[0].color)
    expect(colorFor(4, steps)).toBe(steps[1].color)
    expect(colorFor(12, steps)).toBe(steps[3].color)
  })
  it('copes with a count above the top step', () => {
    expect(colorFor(99, steps)).toBe(steps[3].color)
  })
})

describe('focusBox', () => {
  it('keeps a minimum size around a small cluster', () => {
    const [[w, s], [e, n]] = focusBox([A, B])
    expect(w).toBeCloseTo(-73.0, 5)
    expect(e).toBeCloseTo(-72.7, 5)
    expect(s).toBeCloseTo(41.39, 5)
    expect(n).toBeCloseTo(41.61, 5)
  })
  it('adds a margin around a big cluster', () => {
    const [[w, s], [e, n]] = focusBox([A, C])
    expect(w).toBeCloseTo(-73.075, 5)  // longitude: the 0.30 minimum width wins
    expect(e).toBeCloseTo(-72.775, 5)
    expect(s).toBeCloseTo(41.4325, 5)  // latitude: 0.45 degrees plus a 15% margin on each side wins
    expect(n).toBeCloseTo(42.0175, 5)
  })
})

describe('buildMap', () => {
  it('zooms to the ZIPs that have clients', () => {
    const map = buildMap(FEATURES, report([zip('06410', 3), zip('06492', 1)]))
    expect(inside(find(map, '06410').center)).toBe(true)
    expect(inside(find(map, '06492').center)).toBe(true)
    expect(inside(find(map, '06001').center)).toBe(false)   // the far one is out of view
    expect(find(map, '06001').center[1]).toBeLessThan(0)    // off the top, because it is north
  })

  it('does not zoom tighter than a minimum for a single ZIP', () => {
    const map = buildMap(FEATURES, report([zip('06410', 2)]))
    expect(Math.abs(find(map, '06410').center[0] - MAP_SIZE.width / 2)).toBeLessThan(5)
    expect(inside(find(map, '06492').center)).toBe(true)   // its neighbour stays in view for context
  })

  it('shows the whole state on request', () => {
    const map = buildMap(FEATURES, report([zip('06410', 3)]), { mode: 'state' })
    for (const p of map.paths) expect(inside(p.center)).toBe(true)
  })

  it('shows the whole state when no ZIP has clients', () => {
    const map = buildMap(FEATURES, report([]))
    for (const p of map.paths) expect(inside(p.center)).toBe(true)
    expect(map.maxCount).toBe(0)
    expect(map.steps).toEqual([])
  })

  it('draws every area, and the shaded ones last so their outlines stay on top', () => {
    const map = buildMap(FEATURES, report([zip('06410', 3), zip('06492', 1)]))
    expect(map.paths.map((p) => p.zip)).toEqual(['06001', '06492', '06410'])
    for (const p of map.paths) expect(p.d).toMatch(/^M/)
  })

  it('shades by count and leaves empty areas neutral', () => {
    const map = buildMap(FEATURES, report([zip('06410', 3), zip('06492', 1)]))
    expect(map.maxCount).toBe(3)
    expect(find(map, '06001')).toMatchObject({ count: 0, color: NEUTRAL })
    expect(find(map, '06492')).toMatchObject({ count: 1, color: BLUES[0] })
    expect(find(map, '06410')).toMatchObject({ count: 3, color: BLUES[4] })
  })

  it('reports ZIPs that have clients but no map area', () => {
    const map = buildMap(FEATURES, report([zip('06410', 3), zip('06999', 4)]))
    expect(map.unmapped).toEqual([zip('06999', 4)])
    expect(map.unmappedClients).toBe(4)
    expect(map.maxCount).toBe(3)   // the shading only considers what is drawn
  })

  it('fits the drawn areas inside the frame', () => {
    const map = buildMap(FEATURES, report([]), { width: 400, height: 300, pad: 10 })
    const xs = map.paths.map((p) => p.center[0])
    const ys = map.paths.map((p) => p.center[1])
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(10)
    expect(Math.max(...xs)).toBeLessThanOrEqual(390)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(10)
    expect(Math.max(...ys)).toBeLessThanOrEqual(290)
  })

  it('draws shapes that are wound the right way', () => {
    // A ring wound the wrong way would make d3 fill the entire globe
    const area = geoPath().area(A.geometry)
    expect(area).toBeGreaterThan(0)
    expect(area).toBeLessThan(1)
  })
})

describe('text helpers', () => {
  it('words the tooltip', () => {
    expect(tooltipText('06410', 2)).toBe('06410 · 2 clients')
    expect(tooltipText('06410', 1)).toBe('06410 · 1 client')
    expect(tooltipText('06001', 0)).toBe('06001 · no clients')
  })

  it('summarises a report', () => {
    const r = report([zip('06410', 3), zip('06492', 1)], { other: 2, no_zip: 1, total_clients: 7 })
    expect(summarize(r, 4)).toEqual({ total: 7, connecticut: 4, zipCount: 2, other: 2, noZip: 1, unmapped: 4 })
    expect(summarize(r).unmapped).toBe(0)
  })

  it('lists ZIPs, then the leftovers when there are any', () => {
    const r = report([zip('06410', 3), zip('06492', 1)], { other: 2, no_zip: 1 })
    expect(zipRows(r)).toEqual([
      { key: '06410', label: '06410', clients: 3 },
      { key: '06492', label: '06492', clients: 1 },
      { key: 'other', label: 'Outside Connecticut', clients: 2 },
      { key: 'none', label: 'No ZIP recorded', clients: 1 },
    ])
    expect(zipRows(report([zip('06410', 3)])).map((row) => row.key)).toEqual(['06410'])
  })
})