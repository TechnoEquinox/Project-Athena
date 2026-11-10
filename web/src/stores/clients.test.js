import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useClients } from './clients'

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) }
}

function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

const page = (rows) => ({ clients: rows, total: rows.length, limit: 25, offset: 0 })

let fetchMock
beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
})

describe('clients store', () => {
  it('loads with the query, page size and offset', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([{ client_id: 1 }]))))
    const clients = useClients()
    clients.q = ' ada '
    clients.first = 50
    await clients.load()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/clients?q=ada&limit=25&offset=50')
    expect(clients.rows).toEqual([{ client_id: 1 }])
    expect(clients.total).toBe(1)
  })

  it('leaves out an empty search', async () => {
    fetchMock.mockReturnValue(Promise.resolve(response(200, page([]))))
    await useClients().load()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/clients?limit=25&offset=0')
  })

  it('goes back to the first page when the search changes', () => {
    const clients = useClients()
    clients.setPage(50)
    expect(clients.first).toBe(50)
    clients.setQuery('ada')
    expect(clients.q).toBe('ada')
    expect(clients.first).toBe(0)
  })

  it('ignores a slow answer to an older search', async () => {
    const older = deferred()
    const newer = deferred()
    fetchMock.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const clients = useClients()
    clients.q = 'a'
    const first = clients.load()
    clients.q = 'ab'
    const second = clients.load()
    newer.resolve(response(200, page([{ client_id: 2 }])))
    await second
    older.resolve(response(200, page([{ client_id: 1 }])))
    await first
    expect(clients.rows).toEqual([{ client_id: 2 }])
    expect(clients.loading).toBe(false)
  })

  it('reports loading while a request is running', async () => {
    const pending = deferred()
    fetchMock.mockReturnValue(pending.promise)
    const clients = useClients()
    const running = clients.load()
    expect(clients.loading).toBe(true)
    pending.resolve(response(200, page([])))
    await running
    expect(clients.loading).toBe(false)
  })

  it('shows an error, then recovers on the next load', async () => {
    fetchMock
      .mockReturnValueOnce(Promise.resolve(response(500, {})))
      .mockReturnValueOnce(Promise.resolve(response(200, page([{ client_id: 1 }]))))
    const clients = useClients()
    await clients.load()
    expect(clients.error).toBe('Request failed (500)')
    expect(clients.loading).toBe(false)
    await clients.load()
    expect(clients.error).toBe('')
    expect(clients.rows).toHaveLength(1)
  })
})