import { describe, expect, it } from 'vitest'
import { decide } from './guard'

const signedIn = { ready: true, isAuthenticated: true, mfaSetupRequired: false }

describe('route guard', () => {
  it('sends signed-out users to login', () => {
    expect(decide({ meta: {}, name: 'home' }, { ...signedIn, isAuthenticated: false })).toEqual({
      name: 'login',
    })
  })

  it('lets signed-out users see public pages', () => {
    expect(decide({ meta: { public: true }, name: 'login' }, { ...signedIn, isAuthenticated: false })).toBe(true)
  })

  it('keeps signed-in users off the login page', () => {
    expect(decide({ meta: { public: true }, name: 'login' }, signedIn)).toEqual({ name: 'home' })
  })

  it('lets signed-in users through', () => {
    expect(decide({ meta: {}, name: 'clients' }, signedIn)).toBe(true)
  })

  it('walks users who owe 2FA setup to the security page', () => {
    const pending = { ...signedIn, mfaSetupRequired: true }
    expect(decide({ meta: {}, name: 'home' }, pending)).toEqual({ name: 'security' })
    expect(decide({ meta: {}, name: 'clients' }, pending)).toEqual({ name: 'security' })
  })

  it('lets users who owe 2FA setup reach the security page', () => {
    expect(decide({ meta: {}, name: 'security' }, { ...signedIn, mfaSetupRequired: true })).toBe(true)
  })
})