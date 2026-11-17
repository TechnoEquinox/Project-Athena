// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { describe, expect, it } from 'vitest'
import {
  OPEN_STATUSES, buildCallPayload, callerName, emptyCallForm, hasCaller, isOpen,
  statusSeverity, waitingFor,
} from './calls'

const call = {
  call_id: 4,
  called_at: '2026-01-15T19:30:00+00:00',
  status: 'needs_call',
  client_first_name: 'Zed',
  client_last_name: 'Caller',
  phone: '2035550100',
  notes: 'Left a voicemail',
  tech: { tech_id: 2, first_name: 'Pat', last_name: 'Lee' },
  client: { client_id: 5, first_name: 'Ada', last_name: 'Lovelace' },
}

const blank = {
  status: 'needs_call', when: new Date('2026-01-15T14:30:00-05:00'),
  first_name: '', last_name: '', phone: '', notes: '', client: null, tech_id: null,
}

describe('statuses', () => {
  it('knows which statuses are open', () => {
    expect(OPEN_STATUSES).toEqual(['needs_call', 'needs_email', 'needs_attention'])
    expect(isOpen('needs_email')).toBe(true)
    expect(isOpen('no_action_required')).toBe(false)
    expect(isOpen('outgoing')).toBe(false)
  })

  it('gives each status a tag colour', () => {
    expect(statusSeverity('needs_call')).toBe('warn')
    expect(statusSeverity('needs_attention')).toBe('danger')
    expect(statusSeverity('no_action_required')).toBe('success')
    expect(statusSeverity('whatever')).toBe('secondary')
  })
})

describe('callerName', () => {
  it('prefers the name as typed', () => {
    expect(callerName(call)).toBe('Zed Caller')
  })
  it('falls back to the linked client', () => {
    expect(callerName({ ...call, client_first_name: null, client_last_name: null })).toBe('Ada Lovelace')
  })
  it('handles a single typed name', () => {
    expect(callerName({ ...call, client_last_name: null })).toBe('Zed')
  })
  it('says so when there is no name at all', () => {
    expect(callerName({ client_first_name: null, client_last_name: null, client: null })).toBe('Unknown caller')
  })
})

describe('waitingFor', () => {
  const at = '2026-11-10T12:00:00Z'
  const later = (ms) => new Date(new Date(at).getTime() + ms)
  const MIN = 60 * 1000

  it('says just now for under a minute', () => {
    expect(waitingFor(at, later(30 * 1000))).toBe('just now')
  })
  it('counts minutes, hours and days', () => {
    expect(waitingFor(at, later(MIN))).toBe('1 minute')
    expect(waitingFor(at, later(5 * MIN))).toBe('5 minutes')
    expect(waitingFor(at, later(60 * MIN))).toBe('1 hour')
    expect(waitingFor(at, later(3 * 60 * MIN))).toBe('3 hours')
    expect(waitingFor(at, later(24 * 60 * MIN))).toBe('1 day')
    expect(waitingFor(at, later(50 * 60 * MIN))).toBe('2 days')
  })
  it('never goes negative', () => {
    expect(waitingFor(at, later(-5 * MIN))).toBe('just now')
  })
})

describe('hasCaller', () => {
  it('is false for an empty form', () => {
    expect(hasCaller(blank)).toBe(false)
  })
  it('accepts a client, a name or a phone number', () => {
    expect(hasCaller({ ...blank, client: { client_id: 5, label: 'x' } })).toBe(true)
    expect(hasCaller({ ...blank, first_name: 'Zed' })).toBe(true)
    expect(hasCaller({ ...blank, last_name: 'Caller' })).toBe(true)
    expect(hasCaller({ ...blank, phone: '(203) 555-0100' })).toBe(true)
  })
  it('ignores whitespace and phone text without digits', () => {
    expect(hasCaller({ ...blank, first_name: '   ', phone: 'abc' })).toBe(false)
  })
})

describe('emptyCallForm', () => {
  const NOW = new Date(2026, 10, 10, 13, 45)

  it('starts blank, set to now, with the default tech', () => {
    expect(emptyCallForm(null, { now: NOW, techId: 2 })).toEqual({
      status: null, when: NOW, first_name: '', last_name: '', phone: '', notes: '',
      client: null, tech_id: 2,
    })
  })

  it('prefills from an existing call', () => {
    expect(emptyCallForm(call)).toEqual({
      status: 'needs_call',
      when: new Date('2026-01-15T19:30:00+00:00'),
      first_name: 'Zed', last_name: 'Caller', phone: '(203) 555-0100', notes: 'Left a voicemail',
      client: { client_id: 5, label: 'Lovelace, Ada' },
      tech_id: 2,
    })
  })

  it('copes with a call that has no client, phone or notes', () => {
    const bare = { ...call, client: null, phone: null, notes: null, client_first_name: null, client_last_name: null }
    expect(emptyCallForm(bare)).toMatchObject({ client: null, phone: '', notes: '', first_name: '', last_name: '' })
  })
})

describe('buildCallPayload, creating', () => {
  it('sends the status and the received time', () => {
    expect(buildCallPayload(blank)).toEqual({
      status: 'needs_call', called_at: '2026-01-15T19:30:00.000Z',
    })
  })

  it('leaves the time out while it is still the default of now', () => {
    const now = new Date('2026-11-10T18:00:00Z')
    expect(buildCallPayload({ ...blank, when: new Date(now) }, null, { defaultWhen: now })).toEqual({
      status: 'needs_call',
    })
  })

  it('sends a backdated time even when a default is known', () => {
    const now = new Date('2026-11-10T18:00:00Z')
    expect(buildCallPayload(blank, null, { defaultWhen: now })).toHaveProperty('called_at')
  })

  it('sends trimmed names, phone, notes and the linked client', () => {
    const form = {
      ...blank, first_name: ' Zed ', last_name: ' Caller ', phone: ' (203) 555-0100 ',
      notes: ' Left a voicemail ', client: { client_id: 5, label: 'x' },
    }
    expect(buildCallPayload(form)).toEqual({
      status: 'needs_call', called_at: '2026-01-15T19:30:00.000Z',
      client_first_name: 'Zed', client_last_name: 'Caller', phone: '(203) 555-0100',
      notes: 'Left a voicemail', client_id: 5,
    })
  })

  it('sends the tech only when asked to, which is for admins', () => {
    expect(buildCallPayload({ ...blank, tech_id: 3 }, null, { sendTech: true })).toMatchObject({ tech_id: 3 })
    expect(buildCallPayload({ ...blank, tech_id: 3 })).not.toHaveProperty('tech_id')
  })
})

describe('buildCallPayload, editing', () => {
  const edit = (changes, options) =>
    buildCallPayload({ ...emptyCallForm(call), ...changes }, call, options)

  it('sends nothing when nothing changed', () => {
    expect(edit({})).toEqual({})
  })

  it('closes the loop with just the status', () => {
    expect(edit({ status: 'no_action_required' })).toEqual({ status: 'no_action_required' })
  })

  it('sends only the fields that changed', () => {
    expect(edit({ notes: 'Called back', first_name: 'Zeb' })).toEqual({
      notes: 'Called back', client_first_name: 'Zeb',
    })
  })

  it('ignores phone formatting', () => {
    expect(edit({ phone: '203.555.0100' })).toEqual({})
  })

  it('sends a changed phone number', () => {
    expect(edit({ phone: '203-555-0111' })).toEqual({ phone: '203-555-0111' })
  })

  it('clears optional fields with null', () => {
    expect(edit({ phone: '', notes: '  ', first_name: '', last_name: '' })).toEqual({
      phone: null, notes: null, client_first_name: null, client_last_name: null,
    })
  })

  it('does not clear fields that were already empty', () => {
    const bare = { ...call, phone: null, notes: null, client_first_name: null, client_last_name: null }
    expect(buildCallPayload(emptyCallForm(bare), bare)).toEqual({})
  })

  it('still sends a phone with no digits so the server can reject it', () => {
    expect(edit({ phone: 'abc' })).toEqual({ phone: 'abc' })
  })

  it('sends a changed time', () => {
    expect(edit({ when: new Date('2026-01-16T10:00:00Z') })).toEqual({
      called_at: '2026-01-16T10:00:00.000Z',
    })
  })

  it('links and unlinks a client', () => {
    expect(edit({ client: { client_id: 9, label: 'x' } })).toEqual({ client_id: 9 })
    expect(edit({ client: null })).toEqual({ client_id: null })
    const unlinked = { ...call, client: null }
    expect(buildCallPayload(emptyCallForm(unlinked), unlinked)).toEqual({})
  })

  it('sends a tech change only for admins', () => {
    expect(edit({ tech_id: 9 })).toEqual({})
    expect(edit({ tech_id: 9 }, { sendTech: true })).toEqual({ tech_id: 9 })
    expect(edit({}, { sendTech: true })).toEqual({})
  })
})