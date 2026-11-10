import { defineStore } from 'pinia'
import { api, setCsrf } from '../api'

export const useAuth = defineStore('auth', {
  state: () => ({ user: null, mfaSetupRequired: false, ready: false }),
  getters: {
    isAuthenticated: (state) => state.user !== null,
    isAdmin: (state) => state.user?.role === 'admin',
    canWrite: (state) => !!state.user && ['admin', 'navigator'].includes(state.user.role),
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