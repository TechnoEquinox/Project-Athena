import { geoArea, geoBounds } from 'd3-geo'
import { describe, expect, it } from 'vitest'
import data from './ct-zcta.json'

const zips = data.features.map((f) => f.properties.zip)

describe('Connecticut ZIP areas', () => {
  it('is a collection of features', () => {
    expect(data.type).toBe('FeatureCollection')
    expect(data.features.length).toBeGreaterThanOrEqual(150)
  })

  it('has one area per ZIP, all in the 06xxx range, and nothing else attached', () => {
    expect(new Set(zips).size).toBe(zips.length)
    for (const f of data.features) {
      expect(f.properties.zip).toMatch(/^06\d{3}$/)
      expect(Object.keys(f.properties)).toEqual(['zip'])
    }
  })

  it('includes the ZIPs we know are there', () => {
    expect(zips).toContain('06492')   // Wallingford
    expect(zips).toContain('06410')   // Cheshire
  })

  it('is wound the way d3 expects', () => {
    // All of Connecticut is about 0.0004 steradians. A ring wound the wrong way
    // is read as "everything except this shape", which is about 12.5.
    for (const f of data.features) expect(geoArea(f)).toBeLessThan(0.001)
  })

  it('stays in and around Connecticut', () => {
    for (const f of data.features) {
      const [[west, south], [east, north]] = geoBounds(f)
      expect(west).toBeGreaterThan(-74)
      expect(east).toBeLessThan(-71.5)
      expect(south).toBeGreaterThan(40.8)
      expect(north).toBeLessThan(42.2)
    }
  })
})