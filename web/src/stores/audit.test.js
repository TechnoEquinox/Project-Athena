// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAudit } from './audit'

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }
}

function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

const page = (ids, next = null) => ({
  entries: ids.map((id) => ({ audit_id: id, action: 'x' })),
  next_before_id: next,
})
const ids = (store) => store.entries.map((e) => e.audit_id)

let fetchMock
beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
})

const url = (call = 0) => fetchMock.mock.calls[call][0]

describe('audit store', () => {
  it('loads the first page', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([3, 2], 2))))
    const store = useAudit()
    await store.load()
    expect(url()).toBe('/api/admin/audit?limit=50')
    expect(ids(store)).toEqual([3, 2])
    expect(store.nextBeforeId).toBe(2)
    expect(store.loading).toBe(false)
  })

  it('filters by action', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([]))))
    const store = useAudit()
    store.setAction('login_failed')
    await store.load()
    expect(url()).toBe('/api/admin/audit?action=login_failed&limit=50')
  })

  it('loads older entries after the last one and appends them', async () => {
    fetchMock
      .mockReturnValueOnce(Promise.resolve(response(200, page([3, 2], 2))))
      .mockReturnValueOnce(Promise.resolve(response(200, page([1], null))))
    const store = useAudit()
    await store.load()
    await store.more()
    expect(url(1)).toBe('/api/admin/audit?before_id=2&limit=50')
    expect(ids(store)).toEqual([3, 2, 1])
    expect(store.nextBeforeId).toBeNull()
  })

  it('keeps the filter when loading more', async () => {
    fetchMock
      .mockReturnValueOnce(Promise.resolve(response(200, page([3, 2], 2))))
      .mockReturnValueOnce(Promise.resolve(response(200, page([1]))))
    const store = useAudit()
    store.setAction('login_failed')
    await store.load()
    await store.more()
    expect(url(1)).toBe('/api/admin/audit?action=login_failed&before_id=2&limit=50')
  })

  it('does nothing when there is no older page', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([1], null))))
    const store = useAudit()
    await store.load()
    await store.more()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('ignores a second request for more while one is running', async () => {
    const pending = deferred()
    fetchMock
      .mockReturnValueOnce(Promise.resolve(response(200, page([3, 2], 2))))
      .mockReturnValueOnce(pending.promise)
    const store = useAudit()
    await store.load()
    const first = store.more()
    await store.more()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    pending.resolve(response(200, page([1])))
    await first
    expect(ids(store)).toEqual([3, 2, 1])
  })

  it('replaces the list when the filter changes', async () => {
    fetchMock
      .mockReturnValueOnce(Promise.resolve(response(200, page([3, 2], 2))))
      .mockReturnValueOnce(Promise.resolve(response(200, page([9]))))
    const store = useAudit()
    await store.load()
    store.setAction('logout')
    await store.load()
    expect(ids(store)).toEqual([9])
    expect(store.nextBeforeId).toBeNull()
  })

  it('ignores a slow answer to an older load', async () => {
    const older = deferred()
    const newer = deferred()
    fetchMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const store = useAudit()
    const first = store.load()
    const second = store.load()
    newer.resolve(response(200, page([2])))
    await second
    older.resolve(response(200, page([1])))
    await first
    expect(ids(store)).toEqual([2])
    expect(store.loading).toBe(false)
  })

  it('drops a slow page of older entries if the list was reloaded meanwhile', async () => {
    const slow = deferred()
    fetchMock
      .mockReturnValueOnce(Promise.resolve(response(200, page([3, 2], 2))))
      .mockReturnValueOnce(slow.promise)
      .mockReturnValueOnce(Promise.resolve(response(200, page([9]))))
    const store = useAudit()
    await store.load()
    const more = store.more()
    await store.load()
    slow.resolve(response(200, page([1])))
    await more
    expect(ids(store)).toEqual([9])
  })

  it('shows an error, then recovers on the next load', async () => {
    fetchMock
      .mockReturnValueOnce(Promise.resolve(response(500, {})))
      .mockReturnValueOnce(Promise.resolve(response(200, page([1]))))
    const store = useAudit()
    await store.load()
    expect(store.error).toBe('Request failed (500)')
    await store.load()
    expect(store.error).toBe('')
    expect(ids(store)).toEqual([1])
  })
})