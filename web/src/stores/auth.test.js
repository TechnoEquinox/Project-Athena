import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api, setCsrf } from '../api'
import { useAuth } from './auth'

const USER = { user_id: 1, username: 'boss', role: 'admin', tech_id: null, two_factor_enabled: true }
const SESSION = { user: USER, csrf_token: 'csrf-1', mfa_setup_required: false }

function reply(status, body) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
}

let fetchMock
beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
  setCsrf(null)
})

describe('auth store', () => {
  it('signs in without 2FA and arms the CSRF header', async () => {
    fetchMock.mockReturnValueOnce(reply(200, SESSION)).mockReturnValueOnce(reply(200, {}))
    const auth = useAuth()
    expect(await auth.login('boss', 'pw')).toBe('ok')
    expect(auth.isAuthenticated).toBe(true)
    await api.post('/api/anything', {})
    expect(fetchMock.mock.calls[1][1].headers['X-CSRF-Token']).toBe('csrf-1')
  })

  it('stops at the code step for a 2FA user', async () => {
    fetchMock.mockReturnValue(reply(200, { mfa_required: true }))
    const auth = useAuth()
    expect(await auth.login('boss', 'pw')).toBe('mfa')
    expect(auth.isAuthenticated).toBe(false)
  })

  it('finishes login with an authenticator code', async () => {
    fetchMock.mockReturnValue(reply(200, SESSION))
    const auth = useAuth()
    await auth.submitCode({ code: '123456' })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/login/totp')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ code: '123456' })
    expect(auth.isAuthenticated).toBe(true)
  })

  it('sends a recovery code under its own key', async () => {
    fetchMock.mockReturnValue(reply(200, SESSION))
    await useAuth().submitCode({ recoveryCode: 'abcd-efgh-ijkm-npqr' })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      recovery_code: 'abcd-efgh-ijkm-npqr',
    })
  })

  it('stays signed out and rethrows on a bad password', async () => {
    fetchMock.mockReturnValue(reply(401, { error: 'invalid_credentials', message: 'nope' }))
    const auth = useAuth()
    await expect(auth.login('boss', 'bad')).rejects.toMatchObject({ status: 401 })
    expect(auth.isAuthenticated).toBe(false)
  })

  it('flags a required 2FA setup', async () => {
    fetchMock.mockReturnValue(reply(200, { ...SESSION, mfa_setup_required: true }))
    const auth = useAuth()
    await auth.login('boss', 'pw')
    expect(auth.mfaSetupRequired).toBe(true)
  })

  it('restores a live session on load', async () => {
    fetchMock.mockReturnValue(reply(200, SESSION))
    const auth = useAuth()
    await auth.restore()
    expect(auth.ready).toBe(true)
    expect(auth.user.username).toBe('boss')
  })

  it('treats a 401 on load as signed out', async () => {
    fetchMock.mockReturnValue(reply(401, { error: 'authentication_required' }))
    const auth = useAuth()
    await auth.restore()
    expect(auth.ready).toBe(true)
    expect(auth.isAuthenticated).toBe(false)
  })

  it('treats a server error on load as signed out without throwing', async () => {
    fetchMock.mockReturnValue(reply(500, {}))
    const auth = useAuth()
    await expect(auth.restore()).resolves.toBeUndefined()
    expect(auth.ready).toBe(true)
    expect(auth.isAuthenticated).toBe(false)
  })

  it('signs out locally even if the server call fails', async () => {
    fetchMock.mockReturnValueOnce(reply(200, SESSION)).mockRejectedValueOnce(new TypeError('x'))
    const auth = useAuth()
    await auth.login('boss', 'pw')
    await auth.logout()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('knows who can write', async () => {
    const auth = useAuth()
    expect(auth.canWrite).toBe(false)
    for (const [role, expected] of [['admin', true], ['navigator', true], ['manager', false]]) {
      auth.user = { ...USER, role }
      expect(auth.canWrite).toBe(expected)
    }
  })
})