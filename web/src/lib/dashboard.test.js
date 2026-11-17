// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { describe, expect, it } from 'vitest'
import {
  INTERVAL_OPTIONS, MODE_OPTIONS, counterCards, formatDay, matchPreset, presetOptions,
  presetRange, rangeLabel, rangeProblem,
} from './dashboard'

const TODAY = '2026-11-12'

describe('presetRange', () => {
  it.each([
    ['thisMonth', { from: '2026-11-01', to: '2026-11-30' }],
    ['thisQuarter', { from: '2026-10-01', to: '2026-12-31' }],
    ['thisYear', { from: '2026-01-01', to: '2026-12-31' }],
    ['lastYear', { from: '2025-01-01', to: '2025-12-31' }],
    ['fiscalYear', { from: '2026-07-01', to: '2027-06-30' }],
    ['lastFiscalYear', { from: '2025-07-01', to: '2026-06-30' }],
  ])('%s', (key, expected) => {
    expect(presetRange(key, TODAY, 7)).toEqual(expected)
  })

  it('puts early-year dates in the fiscal year that began last July', () => {
    expect(presetRange('fiscalYear', '2027-02-10', 7)).toEqual({ from: '2026-07-01', to: '2027-06-30' })
  })

  it('switches fiscal years on the first day', () => {
    expect(presetRange('fiscalYear', '2026-07-01', 7)).toEqual({ from: '2026-07-01', to: '2027-06-30' })
    expect(presetRange('fiscalYear', '2026-06-30', 7)).toEqual({ from: '2025-07-01', to: '2026-06-30' })
  })

  it('treats a January fiscal year as the calendar year', () => {
    expect(presetRange('fiscalYear', TODAY, 1)).toEqual({ from: '2026-01-01', to: '2026-12-31' })
  })

  it('knows a leap February and quarter edges', () => {
    expect(presetRange('thisMonth', '2028-02-10', 7).to).toBe('2028-02-29')
    expect(presetRange('thisQuarter', '2026-04-01', 7)).toEqual({ from: '2026-04-01', to: '2026-06-30' })
    expect(presetRange('thisQuarter', '2026-03-31', 7)).toEqual({ from: '2026-01-01', to: '2026-03-31' })
  })

  it('rejects an unknown preset', () => {
    expect(() => presetRange('nope', TODAY, 7)).toThrow()
  })
})

describe('presetOptions', () => {
  it('lists the presets with ranges and labels', () => {
    const options = presetOptions(TODAY, 7)
    expect(options.map((o) => o.key)).toEqual([
      'thisMonth', 'thisQuarter', 'thisYear', 'lastYear', 'fiscalYear', 'lastFiscalYear',
    ])
    expect(options[2]).toEqual({ key: 'thisYear', label: 'This year', from: '2026-01-01', to: '2026-12-31' })
    expect(options[4].label).toBe('Fiscal year (Jul 2026 – Jun 2027)')
    expect(options[5].label).toBe('Last fiscal year (Jul 2025 – Jun 2026)')
  })

  it('leaves out the fiscal presets when they would repeat the calendar year', () => {
    expect(presetOptions(TODAY, 1).map((o) => o.key)).toEqual(['thisMonth', 'thisQuarter', 'thisYear', 'lastYear'])
  })
})

describe('matchPreset', () => {
  const options = presetOptions(TODAY, 7)
  it('finds a preset by its range', () => {
    expect(matchPreset('2026-01-01', '2026-12-31', options)).toBe('thisYear')
    expect(matchPreset('2026-07-01', '2027-06-30', options)).toBe('fiscalYear')
  })
  it('calls anything else custom', () => {
    expect(matchPreset('2026-02-01', '2026-02-28', options)).toBe('custom')
  })
})

describe('labels', () => {
  it('formats days and ranges without depending on the browser locale', () => {
    expect(formatDay('2026-01-05')).toBe('Jan 5, 2026')
    expect(rangeLabel('2026-01-01', '2026-12-31')).toBe('Jan 1, 2026 – Dec 31, 2026')
  })
  it('offers the grouping and breakdown choices', () => {
    expect(INTERVAL_OPTIONS.map((o) => o.value)).toEqual(['month', 'quarter', 'year'])
    expect(MODE_OPTIONS.map((o) => o.value)).toEqual(['total', 'tech'])
  })
})

describe('rangeProblem', () => {
  it('accepts a good range, including a single day', () => {
    expect(rangeProblem('2026-01-01', '2026-12-31')).toBe('')
    expect(rangeProblem('2026-05-05', '2026-05-05')).toBe('')
  })
  it('wants both dates', () => {
    expect(rangeProblem(null, '2026-12-31')).toMatch(/start and an end/)
    expect(rangeProblem('2026-01-01', '')).toMatch(/start and an end/)
  })
  it('wants the start before the end', () => {
    expect(rangeProblem('2026-12-31', '2026-01-01')).toMatch(/on or before/)
  })
  it('stops at about ten years, the same limit as the server', () => {
    expect(rangeProblem('2016-01-01', '2026-01-01')).toBe('')
    expect(rangeProblem('2015-12-01', '2026-12-31')).toMatch(/ten years/)
  })
})

describe('counterCards', () => {
  const data = {
    counters: {
      month: { label: 'Nov 2026', count: 12 },
      quarter: { label: '2026 Q4', count: 1234 },
      year: { label: '2026', count: 0 },
    },
  }
  it('makes a card for each period', () => {
    expect(counterCards(data)).toEqual([
      { key: 'month', title: 'This month', period: 'Nov 2026', value: '12' },
      { key: 'quarter', title: 'This quarter', period: '2026 Q4', value: '1,234' },
      { key: 'year', title: 'This year', period: '2026', value: '0' },
    ])
  })
  it('shows dashes until the numbers arrive', () => {
    expect(counterCards(null).map((c) => c.value)).toEqual(['—', '—', '—'])
  })
})