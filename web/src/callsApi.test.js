import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import {
  createCall, deleteCall, getCall, listCalls, listStatuses, updateCall,
} from './callsApi'

function reply(status, body) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
}

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
  setCsrf('tok')
})

const url = () => fetchMock.mock.calls[0][0]
const options = () => fetchMock.mock.calls[0][1]

describe('calls API', () => {
  it('loads the statuses from the server', async () => {
    fetchMock.mockReturnValue(reply(200, { statuses: [{ value: 'needs_call', label: 'NEEDS CALL' }] }))
    expect(await listStatuses()).toEqual([{ value: 'needs_call', label: 'NEEDS CALL' }])
    expect(url()).toBe('/api/calls/statuses')
  })

  it('lists the callback queue', async () => {
    fetchMock.mockReturnValue(reply(200, { calls: [], total: 0, limit: 25, offset: 0 }))
    await listCalls({ open: true, order: 'asc', limit: 25, offset: 0 })
    expect(url()).toBe('/api/calls?open=true&order=asc&limit=25&offset=0')
  })

  it('lists with every filter, in a fixed order', async () => {
    fetchMock.mockReturnValue(reply(200, { calls: [], total: 0, limit: 25, offset: 0 }))
    await listCalls({
      status: 'needs_email', tech_id: 2, client_id: 5, unlinked: true,
      from: 'a', to: 'b', order: 'desc', limit: 25, offset: 50,
    })
    expect(url()).toBe(
      '/api/calls?status=needs_email&tech_id=2&client_id=5&unlinked=true&from=a&to=b&order=desc&limit=25&offset=50',
    )
  })

  it('leaves out empty filters', async () => {
    fetchMock.mockReturnValue(reply(200, { calls: [], total: 0, limit: 1, offset: 0 }))
    await listCalls({ status: null, tech_id: undefined, limit: 1, offset: 0 })
    expect(url()).toBe('/api/calls?limit=1&offset=0')
  })

  it('unwraps a single call', async () => {
    fetchMock.mockReturnValue(reply(200, { call: { call_id: 4 } }))
    expect(await getCall(4)).toEqual({ call_id: 4 })
    expect(url()).toBe('/api/calls/4')
  })

  it('creates with a POST', async () => {
    fetchMock.mockReturnValue(reply(201, { call: { call_id: 1 } }))
    expect(await createCall({ status: 'needs_call' })).toEqual({ call_id: 1 })
    expect(options().method).toBe('POST')
    expect(JSON.parse(options().body)).toEqual({ status: 'needs_call' })
  })

  it('updates with a PATCH', async () => {
    fetchMock.mockReturnValue(reply(200, { call: { call_id: 4 } }))
    await updateCall(4, { status: 'no_action_required' })
    expect(url()).toBe('/api/calls/4')
    expect(options().method).toBe('PATCH')
  })

  it('deletes', async () => {
    fetchMock.mockReturnValue(reply(200, { status: 'ok' }))
    expect(await deleteCall(4)).toBeUndefined()
    expect(options().method).toBe('DELETE')
  })

  it("lists one client's calls, newest first", async () => {
    fetchMock.mockReturnValue(reply(200, { calls: [], total: 0, limit: 100, offset: 0 }))
    await listCalls({ client_id: 5, order: 'desc', limit: 100, offset: 0 })
    expect(url()).toBe('/api/calls?client_id=5&order=desc&limit=100&offset=0')
  })
})