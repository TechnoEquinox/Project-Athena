// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { describe, expect, it } from 'vitest'
import { ApiError } from '../api'
import {
  DEVICE_TYPES, LANGUAGES, buildClientPayload, buildDevicePayload, deviceTypeOptions, digitsOf,
  emptyClientForm, emptyDeviceForm, fieldErrorFrom, formatPhone, languageOptions, orderLanguages,
} from './forms'

const client = {
  client_id: 5, first_name: 'Ada', last_name: 'Lovelace', phone: '2035550100',
  email: 'ada@example.com', zipcode: '06492', languages: ['English', 'Spanish'],
}

describe('formatPhone', () => {
  it('formats ten digits', () => {
    expect(formatPhone('2035550100')).toBe('(203) 555-0100')
  })
  it('returns an empty string for nothing', () => {
    expect(formatPhone(null)).toBe('')
    expect(formatPhone(undefined)).toBe('')
    expect(formatPhone('')).toBe('')
  })
  it('leaves anything else alone', () => {
    expect(formatPhone('12345')).toBe('12345')
  })
})

describe('digitsOf', () => {
  it('keeps only digits', () => {
    expect(digitsOf('(203) 555-0100')).toBe('2035550100')
    expect(digitsOf(null)).toBe('')
  })
})

describe('client forms', () => {
  it('starts blank for a new client', () => {
    expect(emptyClientForm()).toEqual({
      first_name: '', last_name: '', phone: '', email: '', zipcode: '', languages: [],
    })
  })

  it('prefills from an existing client', () => {
    expect(emptyClientForm(client)).toEqual({
      first_name: 'Ada', last_name: 'Lovelace', phone: '(203) 555-0100',
      email: 'ada@example.com', zipcode: '06492', languages: ['English', 'Spanish'],
    })
  })

  it('creates with only the names when nothing else is filled in', () => {
    const form = { first_name: '  Ada ', last_name: ' Lovelace  ', phone: '  ', email: '', zipcode: '', languages: [] }
    expect(buildClientPayload(form)).toEqual({ first_name: 'Ada', last_name: 'Lovelace' })
  })

  it('creates with every filled-in field', () => {
    expect(buildClientPayload(emptyClientForm(client))).toEqual({
      first_name: 'Ada', last_name: 'Lovelace', phone: '(203) 555-0100',
      email: 'ada@example.com', zipcode: '06492', languages: ['English', 'Spanish'],
    })
  })

  it('sends nothing when an edit changes nothing', () => {
    expect(buildClientPayload(emptyClientForm(client), client)).toEqual({})
  })

  it('sends only the fields that changed', () => {
    const form = { ...emptyClientForm(client), email: 'new@example.com' }
    expect(buildClientPayload(form, client)).toEqual({ email: 'new@example.com' })
  })

  it('clears optional fields with null', () => {
    const form = { ...emptyClientForm(client), phone: '', zipcode: '' }
    expect(buildClientPayload(form, client)).toEqual({ phone: null, zipcode: null })
  })

  it('ignores phone formatting differences', () => {
    const form = { ...emptyClientForm(client), phone: '203.555.0100' }
    expect(buildClientPayload(form, client)).toEqual({})
  })

  it('ignores email case and spacing', () => {
    const form = { ...emptyClientForm(client), email: ' ADA@Example.com ' }
    expect(buildClientPayload(form, client)).toEqual({})
  })

  it('sends a changed or emptied language list', () => {
    const form = emptyClientForm(client)
    expect(buildClientPayload({ ...form, languages: ['English'] }, client)).toEqual({ languages: ['English'] })
    expect(buildClientPayload({ ...form, languages: [] }, client)).toEqual({ languages: [] })
  })

  it('still sends an unusable phone so the server can reject it', () => {
    const form = { ...emptyClientForm({ ...client, phone: null }), phone: 'abc' }
    expect(buildClientPayload(form, { ...client, phone: null })).toEqual({ phone: 'abc' })
  })
})

describe('device forms', () => {
  it('starts blank, or prefilled from a device', () => {
    expect(emptyDeviceForm()).toEqual({ device_type: '', description: '' })
    expect(emptyDeviceForm({ device_type: 'Phone', description: 'iPhone 13' })).toEqual({
      device_type: 'Phone', description: 'iPhone 13',
    })
  })

  it('creates with only a type when there is no description', () => {
    expect(buildDevicePayload({ device_type: ' Phone ', description: '  ' })).toEqual({ device_type: 'Phone' })
  })

  it('creates with a description', () => {
    expect(buildDevicePayload({ device_type: 'Phone', description: 'iPhone 13' })).toEqual({
      device_type: 'Phone', description: 'iPhone 13',
    })
  })

  it('sends nothing when an edit changes nothing', () => {
    const device = { device_type: 'Phone', description: 'iPhone 13' }
    expect(buildDevicePayload(emptyDeviceForm(device), device)).toEqual({})
  })

  it('sends only what changed and clears a description with null', () => {
    const device = { device_type: 'Phone', description: 'iPhone 13' }
    expect(buildDevicePayload({ device_type: 'Tablet', description: 'iPhone 13' }, device)).toEqual({
      device_type: 'Tablet',
    })
    expect(buildDevicePayload({ device_type: 'Phone', description: '' }, device)).toEqual({ description: null })
  })

  it('offers the standard types, plus an existing unusual one', () => {
    expect(deviceTypeOptions()).toEqual(DEVICE_TYPES)
    expect(deviceTypeOptions('phone')).toEqual([...DEVICE_TYPES, 'phone'])
  })

  it('does not repeat a standard type', () => {
    expect(deviceTypeOptions('Tablet')).toEqual(DEVICE_TYPES)
  })
})

describe('fieldErrorFrom', () => {
  it('maps a validation error to its field', () => {
    const err = new ApiError(400, { error: 'validation_failed', field: 'zipcode', message: 'Must be a 5-digit ZIP code.' })
    expect(fieldErrorFrom(err)).toEqual({ field: 'zipcode', message: 'Must be a 5-digit ZIP code.' })
  })
  it('returns null for other API errors', () => {
    expect(fieldErrorFrom(new ApiError(500, {}))).toBeNull()
    expect(fieldErrorFrom(new ApiError(409, { error: 'possible_duplicate' }))).toBeNull()
  })
  it('returns null for anything that is not an API error', () => {
    expect(fieldErrorFrom(new Error('x'))).toBeNull()
    expect(fieldErrorFrom(null)).toBeNull()
  })
})

describe('language handling in the client form', () => {
  it('ignores the order languages were picked in', () => {
    const form = { ...emptyClientForm(client), languages: ['Spanish', 'English'] }
    expect(buildClientPayload(form, client)).toEqual({})
  })

  it('ignores letter case in stored languages', () => {
    const lower = { ...client, languages: ['english', 'SPANISH'] }
    expect(emptyClientForm(lower).languages).toEqual(['English', 'Spanish'])
    expect(buildClientPayload(emptyClientForm(lower), lower)).toEqual({})
  })

  it('sends languages in list order when creating', () => {
    const form = { ...emptyClientForm(), first_name: 'A', last_name: 'B', languages: ['Spanish', 'English'] }
    expect(buildClientPayload(form)).toEqual({
      first_name: 'A', last_name: 'B', languages: ['English', 'Spanish'],
    })
  })

  it('keeps a language that is not on the list', () => {
    const odd = { ...client, languages: ['Tagalog'] }
    expect(emptyClientForm(odd).languages).toEqual(['Tagalog'])
    expect(buildClientPayload(emptyClientForm(odd), odd)).toEqual({})
  })
})

describe('language options', () => {
  it('offers the standard list, starting with English, each language once', () => {
    expect(languageOptions()).toEqual(LANGUAGES)
    expect(LANGUAGES[0]).toBe('English')
    expect(new Set(LANGUAGES.map((l) => l.toLowerCase())).size).toBe(LANGUAGES.length)
  })

  it('adds a language that is not on the list', () => {
    expect(languageOptions(['Tagalog'])).toEqual([...LANGUAGES, 'Tagalog'])
  })

  it('does not repeat a listed language, whatever its case', () => {
    expect(languageOptions(['spanish'])).toEqual(LANGUAGES)
  })
})

describe('orderLanguages', () => {
  it('orders by the list, with unknown languages last', () => {
    expect(orderLanguages(['Tagalog', 'Spanish', 'english'])).toEqual(['English', 'Spanish', 'Tagalog'])
  })

  it('removes repeats and blanks', () => {
    expect(orderLanguages(['English', 'english', ' ', ''])).toEqual(['English'])
  })

  it('copes with nothing', () => {
    expect(orderLanguages(null)).toEqual([])
    expect(orderLanguages(undefined)).toEqual([])
  })
})