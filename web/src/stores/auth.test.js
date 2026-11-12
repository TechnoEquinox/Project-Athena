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

    it('takes the rotated CSRF token after a password change', async () => {
    fetchMock
      .mockReturnValueOnce(reply(200, SESSION))
      .mockReturnValueOnce(reply(200, { ...SESSION, csrf_token: 'csrf-2' }))
      .mockReturnValueOnce(reply(200, {}))
    const auth = useAuth()
    await auth.login('boss', 'pw')
    await auth.changePassword('old pw', 'new password 123')
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      current_password: 'old pw',
      new_password: 'new password 123',
    })
    await api.post('/api/anything', {})
    expect(fetchMock.mock.calls[2][1].headers['X-CSRF-Token']).toBe('csrf-2')
  })

  it('starts enrollment and returns the secret without storing it', async () => {
    fetchMock.mockReturnValue(reply(200, { secret: 'ABC', otpauth_uri: 'otpauth://totp/x' }))
    const auth = useAuth()
    const result = await auth.startTotpSetup('pw')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/totp/setup')
    expect(result.secret).toBe('ABC')
    expect(JSON.stringify(auth.$state)).not.toContain('ABC')
  })

  it('finishes enrollment, clears the setup flag and returns the recovery codes', async () => {
    fetchMock
      .mockReturnValueOnce(reply(200, { ...SESSION, mfa_setup_required: true }))
      .mockReturnValueOnce(
        reply(200, {
          user: { ...USER, two_factor_enabled: true },
          csrf_token: 'csrf-1',
          mfa_setup_required: false,
          recovery_codes: ['aaaa-bbbb-cccc-dddd'],
        }),
      )
    const auth = useAuth()
    await auth.login('boss', 'pw')
    expect(auth.mfaSetupRequired).toBe(true)
    const codes = await auth.enableTotp('123456')
    expect(codes).toEqual(['aaaa-bbbb-cccc-dddd'])
    expect(auth.mfaSetupRequired).toBe(false)
    expect(auth.user.two_factor_enabled).toBe(true)
  })

  it('disables two-factor with a password and a code', async () => {
    fetchMock.mockReturnValueOnce(reply(200, { status: 'ok', two_factor_enabled: false }))
    const auth = useAuth()
    auth.user = { ...USER, two_factor_enabled: true }
    await auth.disableTotp('pw', { code: '123456' })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      current_password: 'pw',
      code: '123456',
    })
    expect(auth.user.two_factor_enabled).toBe(false)
  })

  it('regenerates recovery codes with a recovery code as the second factor', async () => {
    fetchMock.mockReturnValue(reply(200, { recovery_codes: ['x'] }))
    const codes = await useAuth().regenerateRecoveryCodes('pw', { recoveryCode: 'abcd-efgh-ijkm-npqr' })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      current_password: 'pw',
      recovery_code: 'abcd-efgh-ijkm-npqr',
    })
    expect(codes).toEqual(['x'])
  })

  it('knows who can view the audit log', () => {
    const auth = useAuth()
    expect(auth.canViewAudit).toBe(false)
    for (const [role, expected] of [['admin', true], ['manager', true], ['navigator', false]]) {
      auth.user = { ...USER, role }
      expect(auth.canViewAudit).toBe(expected)
    }
  })

  it('knows who can see the admin area', () => {
    const auth = useAuth()
    expect(auth.canViewAdmin).toBe(false)
    for (const [role, expected] of [['admin', true], ['manager', true], ['navigator', false]]) {
      auth.user = { ...USER, role }
      expect(auth.canViewAdmin).toBe(expected)
    }
  })
})