// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import {
  createBooking, deleteBooking, getBooking, listAvailability, listBookings, listNavigators,
  listSlots, saveAvailability, updateBooking, createTimeOff, deleteTimeOff, listTimeOff, updateTimeOff,
} from './schedulingApi'

const reply = (status, body) =>
  Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) })

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
  setCsrf('tok')
})
const url = () => fetchMock.mock.calls[0][0]
const options = () => fetchMock.mock.calls[0][1]

describe('scheduling API', () => {
  it('lists and saves availability', async () => {
    fetchMock.mockReturnValue(reply(200, { availability: [{ tech_id: 1 }] }))
    expect(await listAvailability()).toEqual([{ tech_id: 1 }])
    expect(url()).toBe('/api/scheduling/availability')
    fetchMock.mockReturnValue(reply(200, { availability: { tech_id: 1 } }))
    await saveAvailability(1, { color: '#000000' })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/scheduling/availability/1')
    expect(fetchMock.mock.calls[1][1].method).toBe('PUT')
  })

  it('lists navigators', async () => {
    fetchMock.mockReturnValue(reply(200, { navigators: [{ tech_id: 2 }] }))
    expect(await listNavigators()).toEqual([{ tech_id: 2 }])
  })

  it('asks for slots, optionally excluding the booking being moved', async () => {
    fetchMock.mockReturnValue(reply(200, { slots: ['a'], blocked: null }))
    expect(await listSlots({ techId: 3, date: '2030-01-07' })).toEqual({ slots: ['a'], blocked: null })
    expect(url()).toBe('/api/scheduling/slots?tech_id=3&date=2030-01-07')
    await listSlots({ techId: 3, date: '2030-01-07', excludeBookingId: 9 })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/scheduling/slots?tech_id=3&date=2030-01-07&exclude_booking_id=9')
  })

  it('encodes the + in a time zone offset', async () => {
    fetchMock.mockReturnValue(reply(200, { bookings: [] }))
    await listBookings({ from: '2030-01-07T00:00:00+01:00', to: '2030-01-08T00:00:00+01:00', techId: 4 })
    expect(url()).toBe(
      '/api/scheduling/bookings?from=2030-01-07T00%3A00%3A00%2B01%3A00&to=2030-01-08T00%3A00%3A00%2B01%3A00&tech_id=4',
    )
  })

  it('leaves tech_id out for "All"', async () => {
    fetchMock.mockReturnValue(reply(200, { bookings: [] }))
    await listBookings({ from: 'a', to: 'b', techId: null })
    expect(url()).not.toContain('tech_id')
  })

  it('gets, creates, updates and deletes a booking', async () => {
    fetchMock.mockReturnValue(reply(200, { booking: { booking_id: 5 } }))
    expect(await getBooking(5)).toEqual({ booking_id: 5 })
    fetchMock.mockReturnValue(reply(201, { booking: { booking_id: 6 } }))
    await createBooking({ client_id: 1 })
    expect(fetchMock.mock.calls[1][1].method).toBe('POST')
    fetchMock.mockReturnValue(reply(200, { booking: {} }))
    await updateBooking(5, { status: 'cancelled' })
    expect(fetchMock.mock.calls[2][1].method).toBe('PATCH')
    fetchMock.mockReturnValue(reply(200, { status: 'ok' }))
    await deleteBooking(5)
    expect(fetchMock.mock.calls[3][1].method).toBe('DELETE')
  })

  it('surfaces a slot conflict as an error with a code', async () => {
    fetchMock.mockReturnValue(reply(409, { error: 'slot_unavailable', message: 'gone' }))
    await expect(createBooking({})).rejects.toMatchObject({ status: 409, code: 'slot_unavailable' })
  })

  it('reports why a day has no slots', async () => {
    fetchMock.mockReturnValue(reply(200, { slots: [], blocked: { description: 'Christmas' } }))
    expect((await listSlots({ techId: 3, date: '2030-12-25' })).blocked).toEqual({ description: 'Christmas' })
  })
})

describe('time off API', () => {
  it('lists blocks for a range, optionally for one navigator', async () => {
    fetchMock.mockReturnValue(reply(200, { time_off: [{ time_off_id: 1 }] }))
    expect(await listTimeOff({ from: '2030-01-01', to: '2030-02-01' })).toEqual([{ time_off_id: 1 }])
    expect(url()).toBe('/api/scheduling/time-off?from=2030-01-01&to=2030-02-01')
    await listTimeOff({ from: '2030-01-01', to: '2030-02-01', techId: 4 })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/scheduling/time-off?from=2030-01-01&to=2030-02-01&tech_id=4')
  })

  it('creates, updates and deletes, passing back the booking warning', async () => {
    fetchMock.mockReturnValue(reply(201, { time_off: { time_off_id: 2 }, affected_bookings: 3 }))
    expect(await createTimeOff({ description: 'x' })).toEqual({ time_off: { time_off_id: 2 }, affected_bookings: 3 })
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
    fetchMock.mockReturnValue(reply(200, { time_off: {}, affected_bookings: 0 }))
    await updateTimeOff(2, {})
    expect(fetchMock.mock.calls[1][0]).toBe('/api/scheduling/time-off/2')
    expect(fetchMock.mock.calls[1][1].method).toBe('PUT')
    fetchMock.mockReturnValue(reply(200, { status: 'ok' }))
    await deleteTimeOff(2)
    expect(fetchMock.mock.calls[2][1].method).toBe('DELETE')
  })

  it('surfaces a validation error with its message', async () => {
    fetchMock.mockReturnValue(reply(400, { error: 'validation_failed', field: 'description', message: 'Add a short description' }))
    await expect(createTimeOff({})).rejects.toMatchObject({ status: 400 })
  })
})