import { defineStore } from 'pinia'
import { api, setCsrf } from '../api'

export const useAuth = defineStore('auth', {
  state: () => ({ user: null, mfaSetupRequired: false, ready: false }),
  getters: {
    isAuthenticated: (state) => state.user !== null,
    isAdmin: (state) => state.user?.role === 'admin',
    canWrite: (state) => !!state.user && ['admin', 'navigator'].includes(state.user.role),
    canViewAudit: (state) => !!state.user && ['admin', 'manager'].includes(state.user.role),
    canViewAdmin: (state) => !!state.user && ['admin', 'manager'].includes(state.user.role),
  },
  actions: {
    accept(payload) {
      setCsrf(payload.csrf_token)
      this.user = payload.user
      this.mfaSetupRequired = !!payload.mfa_setup_required
    },
    clear() {
      setCsrf(null)
      this.user = null
      this.mfaSetupRequired = false
    },
    async restore() {
      try {
        this.accept(await api.get('/api/auth/me'))
      } catch {
        this.clear()   // not signed in, or the server is unreachable: show the login screen
      } finally {
        this.ready = true
      }
    },
    async login(username, password) {
      const data = await api.post('/api/auth/login', { username, password })
      if (data.mfa_required) return 'mfa'
      this.accept(data)
      return 'ok'
    },
    async submitCode({ code, recoveryCode }) {
      const body = recoveryCode ? { recovery_code: recoveryCode } : { code }
      this.accept(await api.post('/api/auth/login/totp', body))
    },
    async changePassword(currentPassword, newPassword) {
      // The server rotates the session, so the response carries a fresh cookie and CSRF token
      this.accept(
        await api.post('/api/auth/change-password', {
          current_password: currentPassword,
          new_password: newPassword,
        }),
      )
    },
    async startTotpSetup(currentPassword) {
      // The secret goes straight to the caller and is never kept in the store
      return api.post('/api/auth/totp/setup', { current_password: currentPassword })
    },
    async enableTotp(code) {
      const data = await api.post('/api/auth/totp/enable', { code })
      this.accept(data)
      return data.recovery_codes
    },
    async disableTotp(currentPassword, { code, recoveryCode }) {
      const second = recoveryCode ? { recovery_code: recoveryCode } : { code }
      await api.post('/api/auth/totp/disable', { current_password: currentPassword, ...second })
      this.user = { ...this.user, two_factor_enabled: false }
    },
    async regenerateRecoveryCodes(currentPassword, { code, recoveryCode }) {
      const second = recoveryCode ? { recovery_code: recoveryCode } : { code }
      const data = await api.post('/api/auth/totp/recovery-codes', {
        current_password: currentPassword,
        ...second,
      })
      return data.recovery_codes
    },
    async logout() {
      try {
        await api.post('/api/auth/logout')
      } catch {
        // already signed out on the server, or unreachable: sign out here either way
      } finally {
        this.clear()
      }
    },
  },
})