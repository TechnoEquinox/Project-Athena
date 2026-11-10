import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, qs, setCsrf, setUnauthorizedHandler } from './api'

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
  setCsrf(null)
  setUnauthorizedHandler(() => {})
})

describe('api client', () => {
  it('sends cookies but no CSRF header on GET', async () => {
    setCsrf('tok')
    fetchMock.mockReturnValue(reply(200, { ok: true }))
    await api.get('/api/clients')
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/clients')
    expect(options.credentials).toBe('same-origin')
    expect(options.headers['X-CSRF-Token']).toBeUndefined()
  })

  it('sends the CSRF header and a JSON body on writes', async () => {
    setCsrf('tok')
    fetchMock.mockReturnValue(reply(200, {}))
    await api.post('/api/clients', { a: 1 })
    const options = fetchMock.mock.calls[0][1]
    expect(options.method).toBe('POST')
    expect(options.headers['X-CSRF-Token']).toBe('tok')
    expect(options.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(options.body)).toEqual({ a: 1 })
  })

  it.each(['patch', 'delete'])('sends the CSRF header on %s', async (verb) => {
    setCsrf('tok')
    fetchMock.mockReturnValue(reply(200, {}))
    await api[verb]('/api/x', verb === 'patch' ? { a: 1 } : undefined)
    expect(fetchMock.mock.calls[0][1].headers['X-CSRF-Token']).toBe('tok')
  })

  it('sends no CSRF header before one is known', async () => {
    fetchMock.mockReturnValue(reply(200, {}))
    await api.post('/api/auth/login', { username: 'a', password: 'b' })
    expect(fetchMock.mock.calls[0][1].headers['X-CSRF-Token']).toBeUndefined()
  })

  it('throws an ApiError carrying status, code and body', async () => {
    fetchMock.mockReturnValue(
      reply(400, { error: 'validation_failed', field: 'phone', message: 'Bad phone' }),
    )
    const err = await api.post('/x', {}).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(400)
    expect(err.code).toBe('validation_failed')
    expect(err.message).toBe('Bad phone')
    expect(err.body.field).toBe('phone')
  })

  it('survives an error response that is not JSON', async () => {
    fetchMock.mockReturnValue(
      Promise.resolve({ ok: false, status: 502, json: () => Promise.reject(new Error('no')) }),
    )
    const err = await api.get('/x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(502)
  })

  it('reports a network failure as status 0', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const err = await api.get('/x').catch((e) => e)
    expect(err.status).toBe(0)
    expect(err.message).toMatch(/reach the server/i)
  })

  it('calls the unauthorized handler on a 401', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    fetchMock.mockReturnValue(reply(401, { error: 'authentication_required' }))
    await api.get('/api/clients').catch(() => {})
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it.each(['/api/auth/login', '/api/auth/login/totp', '/api/auth/me'])(
    'does not treat a 401 from %s as an expired session',
    async (path) => {
      const handler = vi.fn()
      setUnauthorizedHandler(handler)
      fetchMock.mockReturnValue(reply(401, { error: 'invalid_credentials' }))
      await api.post(path, {}).catch(() => {})
      expect(handler).not.toHaveBeenCalled()
    },
  )
})

describe('qs', () => {
  it('builds a query string and skips empty values', () => {
    expect(qs({ q: 'ada', limit: 25, x: '', y: null, z: undefined })).toBe('?q=ada&limit=25')
  })
  it('returns an empty string for no parameters', () => {
    expect(qs({})).toBe('')
  })
  it('encodes a plus sign so time zone offsets survive', () => {
    expect(qs({ from: '2026-01-15T10:00:00+05:00' })).toBe('?from=2026-01-15T10%3A00%3A00%2B05%3A00')
  })
})