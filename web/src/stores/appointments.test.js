// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { yearRange } from '../lib/appointments'
import { useAppointments } from './appointments'

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }
}

function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

const page = (rows) => ({ appointments: rows, total: rows.length, limit: 25, offset: 0 })

let fetchMock
beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
})

const sent = (call = 0) => new URL(fetchMock.mock.calls[call][0], 'http://x')

describe('appointments store', () => {
  it('starts on the current calendar year', () => {
    expect(useAppointments().range).toEqual(yearRange(new Date()))
  })

  it('loads with the range, filters and paging', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([{ appointment_id: 1 }]))))
    const store = useAppointments()
    store.range = [new Date(2026, 0, 1), new Date(2026, 11, 31)]
    store.techId = 2
    store.locationId = 3
    store.first = 50
    await store.load()
    expect(sent().pathname).toBe('/api/appointments')
    expect(Object.fromEntries(sent().searchParams)).toEqual({
      from: new Date(2026, 0, 1).toISOString(),
      to: new Date(2027, 0, 1).toISOString(),
      tech_id: '2', location_id: '3', limit: '25', offset: '50',
    })
    expect(store.rows).toEqual([{ appointment_id: 1 }])
    expect(store.total).toBe(1)
  })

  it('leaves out empty filters and an empty range', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([]))))
    const store = useAppointments()
    store.range = null
    await store.load()
    expect(Object.fromEntries(sent().searchParams)).toEqual({ limit: '25', offset: '0' })
  })

  it('goes back to the first page when a filter changes', () => {
    const store = useAppointments()
    store.setPage(50)
    store.setTech(2)
    expect([store.first, store.techId]).toEqual([0, 2])
    store.setPage(50)
    store.setLocation(3)
    expect([store.first, store.locationId]).toEqual([0, 3])
    store.setPage(50)
    store.setRange(null)
    expect([store.first, store.range]).toEqual([0, null])
  })

  it('ignores a slow answer to an older request', async () => {
    const older = deferred()
    const newer = deferred()
    fetchMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const store = useAppointments()
    const first = store.load()
    const second = store.load()
    newer.resolve(response(200, page([{ appointment_id: 2 }])))
    await second
    older.resolve(response(200, page([{ appointment_id: 1 }])))
    await first
    expect(store.rows).toEqual([{ appointment_id: 2 }])
    expect(store.loading).toBe(false)
  })

  it('shows an error, then recovers on the next load', async () => {
    fetchMock
      .mockReturnValueOnce(Promise.resolve(response(500, {})))
      .mockReturnValueOnce(Promise.resolve(response(200, page([{ appointment_id: 1 }]))))
    const store = useAppointments()
    await store.load()
    expect(store.error).toBe('Request failed (500)')
    await store.load()
    expect(store.error).toBe('')
    expect(store.rows).toHaveLength(1)
  })
})