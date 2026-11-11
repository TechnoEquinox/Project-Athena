import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCalls } from './calls'

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }
}

function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

const page = (rows) => ({ calls: rows, total: rows.length, limit: 25, offset: 0 })

let fetchMock
beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
})

const sent = (call = 0) => Object.fromEntries(new URL(fetchMock.mock.calls[call][0], 'http://x').searchParams)

describe('calls store', () => {
  it('starts as the callback queue with no filters', () => {
    const store = useCalls()
    expect(store.mode).toBe('queue')
    expect(store.range).toBeNull()
    expect(store.status).toBeNull()
  })

  it('loads open calls oldest first in queue mode', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([{ call_id: 1 }]))))
    const store = useCalls()
    await store.load()
    expect(sent()).toEqual({ open: 'true', order: 'asc', limit: '25', offset: '0' })
    expect(store.rows).toEqual([{ call_id: 1 }])
    expect(store.total).toBe(1)
  })

  it('uses only the tech filter in queue mode', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([]))))
    const store = useCalls()
    store.status = 'needs_email'
    store.range = [new Date(2026, 0, 1), new Date(2026, 11, 31)]
    store.techId = 2
    await store.load()
    expect(sent()).toEqual({ open: 'true', order: 'asc', tech_id: '2', limit: '25', offset: '0' })
  })

  it('loads newest first with every filter in all-calls mode', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([]))))
    const store = useCalls()
    store.setMode('all')
    store.status = 'needs_email'
    store.techId = 2
    store.range = [new Date(2026, 0, 1), new Date(2026, 11, 31)]
    store.first = 50
    await store.load()
    expect(sent()).toEqual({
      status: 'needs_email', order: 'desc', tech_id: '2',
      from: new Date(2026, 0, 1).toISOString(), to: new Date(2027, 0, 1).toISOString(),
      limit: '25', offset: '50',
    })
  })

  it('sends nothing extra when all-calls mode has no filters', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([]))))
    const store = useCalls()
    store.setMode('all')
    store.first = 0
    await store.load()
    expect(sent()).toEqual({ order: 'desc', limit: '25', offset: '0' })
  })

  it('goes back to the first page when anything changes', () => {
    const store = useCalls()
    for (const change of [
      () => store.setMode('all'),
      () => store.setStatus('outgoing'),
      () => store.setTech(2),
      () => store.setRange(null),
    ]) {
      store.setPage(50)
      change()
      expect(store.first).toBe(0)
    }
  })

  it('ignores a slow answer to an older request', async () => {
    const older = deferred()
    const newer = deferred()
    fetchMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const store = useCalls()
    const first = store.load()
    const second = store.load()
    newer.resolve(response(200, page([{ call_id: 2 }])))
    await second
    older.resolve(response(200, page([{ call_id: 1 }])))
    await first
    expect(store.rows).toEqual([{ call_id: 2 }])
    expect(store.loading).toBe(false)
  })

  it('shows an error, then recovers on the next load', async () => {
    fetchMock
      .mockReturnValueOnce(Promise.resolve(response(500, {})))
      .mockReturnValueOnce(Promise.resolve(response(200, page([{ call_id: 1 }]))))
    const store = useCalls()
    await store.load()
    expect(store.error).toBe('Request failed (500)')
    await store.load()
    expect(store.error).toBe('')
    expect(store.rows).toHaveLength(1)
  })
})