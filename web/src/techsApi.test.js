import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listTechs } from './techsApi'

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn().mockReturnValue(
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ techs: [{ tech_id: 1 }] }) }),
  )
  globalThis.fetch = fetchMock
})

describe('techs API', () => {
  it('lists active techs by default', async () => {
    expect(await listTechs()).toEqual([{ tech_id: 1 }])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/techs')
  })

  it('can include inactive techs', async () => {
    await listTechs({ includeInactive: true })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/techs?include_inactive=true')
  })
})