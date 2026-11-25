// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { describe, expect, it } from 'vitest'
import { ApiError } from '../api'
import {
  ADMIN_TABS, AUDIT_ACTIONS, ROLE_OPTIONS, actorLabel, adminErrorMessage, adminTabsFor,
  buildTechPayload, buildUserPayload, emptyTechForm, formatDetail, formatYmd, humanizeAction,
  linkableTechs, parseYmd, resolveAdminTab, restoreSeverity, restoreWindowText, roleLabel,
  showDate, statusText, targetLabel, techName, userFormProblem, userStatus,
} from './admin'

describe('roles', () => {
  it('offers the three roles', () => {
    expect(ROLE_OPTIONS.map((r) => r.value)).toEqual(['admin', 'manager', 'navigator'])
  })
  it('labels a role', () => {
    expect(roleLabel('navigator')).toBe('Navigator')
    expect(roleLabel('auditor')).toBe('auditor')
    expect(roleLabel(null)).toBe('')
  })
})

describe('userStatus', () => {
  const base = { is_active: true, locked: false, lockout_requires_admin: false }
  it('is active by default', () => {
    expect(userStatus(base)).toEqual({ label: 'Active', severity: 'success' })
  })
  it('shows a timed lock', () => {
    expect(userStatus({ ...base, locked: true })).toEqual({ label: 'Locked', severity: 'warn' })
  })
  it('shows a lock that needs an admin', () => {
    expect(userStatus({ ...base, locked: true, lockout_requires_admin: true })).toEqual({
      label: 'Locked (admin reset needed)', severity: 'danger',
    })
  })
  it('shows inactive ahead of everything else', () => {
    expect(userStatus({ ...base, is_active: false, locked: true })).toEqual({
      label: 'Inactive', severity: 'secondary',
    })
  })
})

describe('userFormProblem', () => {
  const good = { username: 'pat', password: 'correct horse battery', role: 'manager', tech_id: null }
  it('accepts a complete form', () => {
    expect(userFormProblem(good)).toBe('')
  })
  it('wants a username of at least three characters', () => {
    expect(userFormProblem({ ...good, username: 'pa' })).toMatch(/at least 3/)
  })
  it('rejects characters the server will not accept', () => {
    expect(userFormProblem({ ...good, username: 'pat lee' })).toMatch(/lowercase/)
    expect(userFormProblem({ ...good, username: 'x'.repeat(65) })).toMatch(/lowercase/)
  })
  it('accepts capitals and spaces around the name, which are cleaned up on save', () => {
    expect(userFormProblem({ ...good, username: '  Pat.Lee ' })).toBe('')
  })
  it('wants a role', () => {
    expect(userFormProblem({ ...good, role: null })).toMatch(/role/i)
  })
  it('wants a tech for a navigator only', () => {
    expect(userFormProblem({ ...good, role: 'navigator' })).toMatch(/tech/i)
    expect(userFormProblem({ ...good, role: 'navigator', tech_id: 3 })).toBe('')
    expect(userFormProblem({ ...good, role: 'admin' })).toBe('')
  })
  it('wants a password of at least 12 characters', () => {
    expect(userFormProblem({ ...good, password: 'short' })).toMatch(/12/)
    expect(userFormProblem({ ...good, password: 'a'.repeat(12) })).toBe('')
  })
})

describe('buildUserPayload', () => {
  it('cleans the username and leaves the password exactly as typed', () => {
    expect(
      buildUserPayload({ username: '  Pat.Lee ', password: ' spaced password ', role: 'manager', tech_id: null }),
    ).toEqual({ username: 'pat.lee', password: ' spaced password ', role: 'manager' })
  })
  it('includes the tech when one is chosen', () => {
    expect(buildUserPayload({ username: 'kim', password: 'x'.repeat(12), role: 'navigator', tech_id: 3 })).toEqual({
      username: 'kim', password: 'x'.repeat(12), role: 'navigator', tech_id: 3,
    })
  })
})

describe('techs for the user form', () => {
  const techs = [
    { tech_id: 1, first_name: 'Pat', last_name: 'Lee', is_active: true, login_role: null },
    { tech_id: 2, first_name: 'Ann', last_name: 'Admin', is_active: true, login_role: 'admin' },
    { tech_id: 3, first_name: 'Old', last_name: 'Timer', is_active: false, login_role: null },
  ]
  it('offers only active techs that have no login yet', () => {
    expect(linkableTechs(techs)).toEqual([{ tech_id: 1, label: 'Lee, Pat' }])
  })
  it('finds a tech name by id', () => {
    expect(techName(techs, 2)).toBe('Ann Admin')
    expect(techName(techs, null)).toBe('')
    expect(techName(techs, 99)).toBe('')
  })
})

describe('dates', () => {
  it('formats and parses a plain date in local time', () => {
    expect(formatYmd(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05')
    expect(parseYmd('2026-01-05')).toEqual(new Date(2026, 0, 5))
  })
  it('shows a plain date without shifting a day', () => {
    expect(showDate('2025-03-01')).toBe(new Date(2025, 2, 1).toLocaleDateString())
    expect(showDate(null)).toBe('')
  })
})

describe('tech forms', () => {
  const tech = { tech_id: 2, first_name: 'Pat', last_name: 'Lee', start_date: '2025-03-01' }

  it('starts blank with today as the start date', () => {
    expect(emptyTechForm(null, { now: new Date(2026, 10, 11, 15, 30) })).toEqual({
      first_name: '', last_name: '', start_date: new Date(2026, 10, 11),
    })
  })
  it('prefills from an existing tech', () => {
    expect(emptyTechForm(tech)).toEqual({
      first_name: 'Pat', last_name: 'Lee', start_date: new Date(2025, 2, 1),
    })
  })
  it('creates with trimmed names and a plain date', () => {
    expect(
      buildTechPayload({ first_name: ' Pat ', last_name: ' Lee ', start_date: new Date(2025, 2, 1, 18, 0) }),
    ).toEqual({ first_name: 'Pat', last_name: 'Lee', start_date: '2025-03-01' })
  })
  it('sends nothing when an edit changes nothing', () => {
    expect(buildTechPayload(emptyTechForm(tech), tech)).toEqual({})
  })
  it('sends only what changed', () => {
    const form = { ...emptyTechForm(tech), last_name: 'Leigh', start_date: new Date(2025, 5, 1) }
    expect(buildTechPayload(form, tech)).toEqual({ last_name: 'Leigh', start_date: '2025-06-01' })
  })
})

describe('restore window', () => {
  const DAY = 24 * 60 * 60 * 1000
  const now = new Date('2026-11-10T12:00:00Z')
  const until = (ms) => new Date(now.getTime() + ms).toISOString()

  it('says how long is left', () => {
    expect(restoreWindowText(until(29.5 * DAY), now)).toBe('29 days')
    expect(restoreWindowText(until(1.5 * DAY), now)).toBe('1 day')
    expect(restoreWindowText(until(0.5 * DAY), now)).toBe('Less than a day')
    expect(restoreWindowText(until(0), now)).toBe('Expired')
    expect(restoreWindowText(until(-DAY), now)).toBe('Expired')
  })
  it('flags records that are close to the end', () => {
    expect(restoreSeverity(until(2 * DAY), now)).toBe('danger')
    expect(restoreSeverity(until(5 * DAY), now)).toBe('warn')
    expect(restoreSeverity(until(20 * DAY), now)).toBe('secondary')
    expect(restoreSeverity(until(-1), now)).toBe('danger')
  })
})

describe('statusText', () => {
  it('turns a stored status into its label', () => {
    expect(statusText('needs_call')).toBe('NEEDS CALL')
    expect(statusText('no_action_required')).toBe('NO ACTION REQUIRED')
  })
})

describe('audit wording', () => {
  it('turns an action into words', () => {
    expect(humanizeAction('login_failed')).toBe('Login failed')
    expect(humanizeAction('totp_enabled')).toBe('2FA enabled')
    expect(humanizeAction('user_totp_reset')).toBe('User 2FA reset')
    expect(humanizeAction('retention_purge')).toBe('Retention purge')
  })
  it('lists every known action once, and each can be turned into words', () => {
    expect(new Set(AUDIT_ACTIONS).size).toBe(AUDIT_ACTIONS.length)
    expect(AUDIT_ACTIONS).toEqual(expect.arrayContaining(['login_failed', 'client_deleted', 'call_restored', 'server_job_requested', 'server_action_failed']))
    for (const action of AUDIT_ACTIONS) expect(humanizeAction(action)).not.toMatch(/_/)
  })
  it('shows who did it', () => {
    expect(actorLabel({ actor_username: 'boss' })).toBe('boss')
    expect(actorLabel({ actor_username: null })).toBe('—')
  })
  it('shows what it was done to', () => {
    expect(targetLabel({ target_type: 'client', target_id: '5' })).toBe('client #5')
    expect(targetLabel({ target_type: null, target_id: null })).toBe('')
  })
  it('summarises the details', () => {
    expect(formatDetail({ fields: ['email', 'phone'], client_id: 5 })).toBe('fields: email, phone · client id: 5')
    expect(formatDetail({ reason: 'bad_password', failed_count: 1 })).toBe('reason: bad_password · failed count: 1')
    expect(formatDetail({ forced_duplicate: true })).toBe('forced duplicate: true')
    expect(formatDetail({ outer: { a: 1 } })).toBe('outer: {"a":1}')
    expect(formatDetail(null)).toBe('')
    expect(formatDetail({})).toBe('')
  })
})

describe('adminErrorMessage', () => {
  it.each([
    ['cannot_deactivate_self', /your own account/],
    ['cannot_reset_own_totp', /another admin/],
    ['use_change_password', /Security page/],
    ['cannot_deactivate_own_tech', /your own login/],
    ['not_found', /no longer exists/],
    ['retention_expired', /past the retention/],
    ['client_deleted', /Restore the client first/],
  ])('explains %s', (code, expected) => {
    expect(adminErrorMessage(new ApiError(400, { error: code, message: 'raw' }))).toMatch(expected)
  })

  it("uses the server's own words for validation problems", () => {
    expect(adminErrorMessage(new ApiError(400, { error: 'weak_password', message: 'Password must be at least 12 characters.' }))).toBe(
      'Password must be at least 12 characters.',
    )
  })
  it('copes with anything else', () => {
    expect(adminErrorMessage(new Error('boom'))).toBe('boom')
    expect(adminErrorMessage(null)).toBe('Something went wrong.')
  })
})

describe('admin tabs', () => {
  it('shows an admin every tab, in order', () => {
    expect(adminTabsFor('admin').map((t) => t.key)).toEqual([
      'users', 'techs', 'availability', 'locations', 'restore', 'audit', 'maintenance',
    ])
  })
  it('shows a manager only the audit log', () => {
    expect(adminTabsFor('manager').map((t) => t.key)).toEqual(['audit'])
  })
  it('shows a navigator nothing', () => {
    expect(adminTabsFor('navigator')).toEqual([])
    expect(adminTabsFor(undefined)).toEqual([])
  })
  it('gives every tab a label and a unique key', () => {
    expect(new Set(ADMIN_TABS.map((t) => t.key)).size).toBe(ADMIN_TABS.length)
    for (const tab of ADMIN_TABS) expect(tab.label).toBeTruthy()
  })
  it('opens the tab asked for when the role allows it', () => {
    expect(resolveAdminTab('admin', 'restore')).toBe('restore')
    expect(resolveAdminTab('manager', 'audit')).toBe('audit')
  })
  it('falls back to the first allowed tab', () => {
    expect(resolveAdminTab('admin', undefined)).toBe('users')
    expect(resolveAdminTab('admin', 'nonsense')).toBe('users')
    expect(resolveAdminTab('manager', 'users')).toBe('audit')
    expect(resolveAdminTab('manager', undefined)).toBe('audit')
  })
  it('has no tab for a role with none', () => {
    expect(resolveAdminTab('navigator', 'users')).toBeNull()
    expect(resolveAdminTab(undefined, 'users')).toBeNull()
  })
})