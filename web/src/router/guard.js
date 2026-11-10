/** Decide where a navigation should go. Returns true to allow, or a route location to redirect to. */
export function decide(to, auth) {
  if (to.meta.public) return auth.isAuthenticated ? { name: 'home' } : true
  if (!auth.isAuthenticated) return { name: 'login' }
  if (auth.mfaSetupRequired && to.name !== 'security') return { name: 'security' }
  return true
}