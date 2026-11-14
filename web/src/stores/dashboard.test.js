import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDashboard } from './dashboard'

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }
}

function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

const COUNTERS = {
  today: '2026-11-12',
  timezone: 'America/New_York',
  fiscal_year_start_month: 7,
  counters: {
    month: { label: 'Nov 2026', from: '2026-11-01', to: '2026-11-30', count: 3 },
    quarter: { label: '2026 Q4', from: '2026-10-01', to: '2026-12-31', count: 5 },
    year: { label: '2026', from: '2026-01-01', to: '2026-12-31', count: 40 },
  },
}

const BODIES = {
  '/api/stats/counters': COUNTERS,
  '/api/stats/appointments': { tag: 'appointments' },
  '/api/stats/calls': { tag: 'calls' },
  '/api/stats/locations': { tag: 'locations' },
  '/api/stats/devices': { tag: 'devices' },
  '/api/stats/zips': { tag: 'zips' },
}

let fetchMock
// A number in `overrides` means "answer with that error status"
function serve(overrides = {}) {
  fetchMock.mockImplementation((url) => {
    const path = new URL(url, 'http://x').pathname
    const body = path in overrides ? overrides[path] : BODIES[path]
    if (body instanceof Error) return Promise.reject(body)
    if (typeof body === 'number') return Promise.resolve(response(body, {}))
    return Promise.resolve(response(200, body))
  })
}

const urls = () => fetchMock.mock.calls.map((c) => c[0])
const reportUrls = () => urls().filter((u) => !u.startsWith('/api/stats/counters')).sort()

beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
})

afterEach(() => vi.useRealTimers())

describe('dashboard store', () => {
  it('loads the counters, then the reports for this calendar year, by month', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    expect(urls()[0]).toBe('/api/stats/counters')
    expect(reportUrls()).toEqual([
      '/api/stats/appointments?from=2026-01-01&to=2026-12-31&interval=month',
      '/api/stats/calls?from=2026-01-01&to=2026-12-31&interval=month',
      '/api/stats/devices?from=2026-01-01&to=2026-12-31',
      '/api/stats/locations?from=2026-01-01&to=2026-12-31&interval=month',
      '/api/stats/zips?from=2026-01-01&to=2026-12-31',
    ])
  })

  it('keeps what it loaded', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    expect(store.today).toBe('2026-11-12')
    expect(store.timezone).toBe('America/New_York')
    expect(store.fiscalStartMonth).toBe(7)
    expect(store.counters).toEqual(COUNTERS)
    expect([store.preset, store.from, store.to, store.interval, store.mode]).toEqual([
      'thisYear', '2026-01-01', '2026-12-31', 'month', 'total',
    ])
    expect(store.appointments).toEqual({ tag: 'appointments' })
    expect(store.calls).toEqual({ tag: 'calls' })
    expect(store.locations).toEqual({ tag: 'locations' })
    expect(store.devices).toEqual({ tag: 'devices' })
    expect(store.loading).toBe(false)
    expect(store.error).toBe('')
    expect(store.zips).toEqual({ tag: 'zips' })
  })

  it("falls back to the browser's date when the counters cannot load", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 10, 12, 12, 0))
    serve({ '/api/stats/counters': 500 })
    const store = useDashboard()
    await store.init()
    expect(store.countersError).toBe('Request failed (500)')
    expect(store.counters).toBeNull()
    expect(store.from).toBe('2026-01-01')
    expect(reportUrls()).toHaveLength(5)
    expect(store.appointments).toEqual({ tag: 'appointments' })
  })

  it('shows an error when a report fails, then recovers on the next load', async () => {
    serve({ '/api/stats/calls': 500 })
    const store = useDashboard()
    await store.init()
    expect(store.error).toBe('Request failed (500)')
    expect(store.loading).toBe(false)
    serve()
    await store.loadReports()
    expect(store.error).toBe('')
    expect(store.calls).toEqual({ tag: 'calls' })
  })

  it('keeps the chosen range when the page is opened again', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    await store.setCustom('2026-02-01', '2026-02-28')
    fetchMock.mockClear()
    await store.init()
    expect(store.from).toBe('2026-02-01')
    expect(reportUrls()[0]).toContain('from=2026-02-01&to=2026-02-28')
  })

  it('switches to a preset range', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    fetchMock.mockClear()
    await store.setPreset('lastYear')
    expect([store.preset, store.from, store.to]).toEqual(['lastYear', '2025-01-01', '2025-12-31'])
    expect(reportUrls()[0]).toBe('/api/stats/appointments?from=2025-01-01&to=2025-12-31&interval=month')
  })

  it('uses the library fiscal year start for the fiscal presets', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    await store.setPreset('fiscalYear')
    expect([store.from, store.to]).toEqual(['2026-07-01', '2027-06-30'])
  })

  it('takes a custom range', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    fetchMock.mockClear()
    await store.setCustom('2026-03-05', '2026-04-10')
    expect(store.preset).toBe('custom')
    expect(reportUrls()[0]).toBe('/api/stats/appointments?from=2026-03-05&to=2026-04-10&interval=month')
  })

  it('recognises a custom range that matches a preset', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    await store.setCustom('2026-07-01', '2027-06-30')
    expect(store.preset).toBe('fiscalYear')
  })

  it('refuses a bad custom range without asking the server', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    fetchMock.mockClear()
    await store.setCustom('2026-12-31', '2026-01-01')
    expect(store.rangeError).toMatch(/on or before/)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(store.from).toBe('2026-01-01')
    await store.setPreset('thisMonth')
    expect(store.rangeError).toBe('')
  })

  it('regroups by quarter', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    fetchMock.mockClear()
    await store.setInterval('quarter')
    expect(reportUrls()[0]).toBe('/api/stats/appointments?from=2026-01-01&to=2026-12-31&interval=quarter')
  })

  it('switching the breakdown needs no new data', async () => {
    serve()
    const store = useDashboard()
    await store.init()
    fetchMock.mockClear()
    store.setMode('tech')
    expect(store.mode).toBe('tech')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('ignores a slow answer to an older request', async () => {
    serve()
    const older = deferred()
    for (let i = 0; i < 5; i++) fetchMock.mockReturnValueOnce(older.promise)
    const store = useDashboard()
    store.from = '2026-01-01'
    store.to = '2026-12-31'
    const first = store.loadReports()    // takes the four slow answers
    const second = store.loadReports()   // answered at once
    await second
    older.resolve(response(200, { tag: 'old' }))
    await first
    expect(store.appointments).toEqual({ tag: 'appointments' })
    expect(store.loading).toBe(false)
  })
})