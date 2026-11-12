import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listAudit } from './auditApi'

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn().mockReturnValue(
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ entries: [], next_before_id: null }),
    }),
  )
  globalThis.fetch = fetchMock
})

describe('audit API', () => {
  it('lists with every parameter, in a fixed order', async () => {
    await listAudit({ action: 'login_failed', before_id: 90, limit: 50 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/audit?action=login_failed&before_id=90&limit=50')
  })

  it('leaves out empty parameters', async () => {
    await listAudit({ action: null, before_id: undefined, limit: 50 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/audit?limit=50')
  })

  it('returns the whole response, including the cursor', async () => {
    expect(await listAudit({ limit: 50 })).toEqual({ entries: [], next_before_id: null })
  })
})