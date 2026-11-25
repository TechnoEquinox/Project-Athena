// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { describe, expect, it } from 'vitest'
import {
  addDaysISO, affectedMessage, buildTimeOffPayload, emptyTimeOffForm, formatDateRange, formFromTimeOff,
  timeOffEvents, timeOffProblem, timeOffWho,
  availabilityProblem, buildAvailabilityPayload, buildDays, buildWindows, colorMap, contactRows,
  cycleWeekNumber, formFromAvailability, mondayOf, parseLocalDate, schedulingErrorMessage, summarize,
  toCalendarEvents, toLocalISODate, WEEKDAYS,
} from './scheduling'

const booking = (over = {}) => ({
  booking_id: 7, starts_at: '2030-01-07T14:00:00+00:00', ends_at: '2030-01-07T14:30:00+00:00',
  status: 'scheduled',
  client: { client_id: 1, first_name: 'Ada', last_name: 'Lovelace' },
  tech: { tech_id: 2, first_name: 'Pat', last_name: 'Lee' }, ...over,
})

describe('toLocalISODate', () => {
  it('uses local fields, so a late evening stays on its own day', () => {
    expect(toLocalISODate(new Date(2030, 0, 7, 23, 30))).toBe('2030-01-07')
    expect(toLocalISODate(new Date(2030, 11, 5, 0, 5))).toBe('2030-12-05')
  })
})

describe('calendar events', () => {
  const colors = colorMap([{ tech_id: 2, color: '#112233' }])
  it('colors by navigator and puts their name in the title', () => {
    const [e] = toCalendarEvents([booking()], colors)
    expect(e).toMatchObject({ id: '7', title: 'Ada Lovelace · Pat', backgroundColor: '#112233', start: '2030-01-07T14:00:00+00:00' })
    expect(e.classNames).toEqual([])
  })
  it('mutes bookings that are not scheduled', () => {
    expect(toCalendarEvents([booking({ status: 'cancelled' })], colors)[0].classNames).toEqual(['booking-cancelled'])
  })
  it('falls back to grey for a navigator with no color', () => {
    expect(toCalendarEvents([booking()], {})[0].backgroundColor).toBe('#64748b')
  })
})

describe('contactRows', () => {
  it('formats what is there and says so when something is missing', () => {
    expect(contactRows({ phone: '2035550100', email: 'a@b.org', languages: ['English', 'Spanish'] })).toEqual([
      { label: 'Phone', value: '(203) 555-0100' },
      { label: 'Email', value: 'a@b.org' },
      { label: 'Language', value: 'English, Spanish' },
    ])
    expect(contactRows({ phone: null, email: null, languages: [] }).map((r) => r.value)).toEqual(
      ['Not on file', 'Not on file', 'Not on file'],
    )
  })
})

describe('availability form', () => {
  const windows = [
    { week: 0, weekday: 0, start_time: '09:00', end_time: '12:00' },
    { week: 0, weekday: 0, start_time: '13:00', end_time: '17:00' },
    { week: 0, weekday: 2, start_time: '10:00', end_time: '14:00' },
  ]
  it('turns windows into a week of days and back', () => {
    const days = buildDays(windows)
    expect(days).toHaveLength(7)
    expect(days[0]).toMatchObject({ weekday: 0, enabled: true })
    expect(days[0].blocks).toHaveLength(2)
    expect(days[1].enabled).toBe(false)
    expect(buildWindows([days])).toEqual(windows)
  })
  it('treats a window with no week as Week 1', () => {
    expect(buildDays([{ weekday: 1, start_time: '09:00', end_time: '10:00' }])[1].enabled).toBe(true)
  })
  it('ignores the blocks of a day that is switched off', () => {
    const days = buildDays(windows)
    days[0].enabled = false
    expect(buildWindows([days]).map((w) => w.weekday)).toEqual([2])
  })
  const form = (over = {}) => ({ ...formFromAvailability({ windows }), ...over })
  it('accepts a good form', () => expect(availabilityProblem(form())).toBe(''))
  it.each([
    [{ appointment_minutes: 4 }, /5 to 240/], [{ appointment_minutes: 30.5 }, /5 to 240/],
    [{ appointment_minutes: null }, /5 to 240/], [{ buffer_minutes: -1 }, /0 to 120/],
    [{ buffer_minutes: 121 }, /0 to 120/], [{ color: 'blue' }, /color/],
  ])('rejects %j', (over, message) => expect(availabilityProblem(form(over))).toMatch(message))
  it('rejects a block that ends before it starts, overlaps, or is missing', () => {
    const weeks = form().weeks
    weeks[0][0].blocks[0] = { start: '12:00', end: '09:00' }
    expect(availabilityProblem(form({ weeks }))).toMatch(/Monday.*end after/)
    const overlap = form().weeks
    overlap[0][0].blocks[1] = { start: '11:00', end: '15:00' }
    expect(availabilityProblem(form({ weeks: overlap }))).toMatch(/overlap/)
    const empty = form().weeks
    empty[0][3].enabled = true
    expect(availabilityProblem(form({ weeks: empty }))).toMatch(/Thursday/)
  })
  it('builds the weekly payload the server expects', () => {
    expect(buildAvailabilityPayload(form({ appointment_minutes: 45, buffer_minutes: 10 }))).toEqual({
      appointment_minutes: 45, buffer_minutes: 10, color: '#2563eb', cycle_weeks: 1, windows,
    })
  })
  it('starts a not-yet-configured navigator on sensible defaults', () => {
    const f = formFromAvailability({ windows: [], appointment_minutes: null, buffer_minutes: null, color: null })
    expect([f.appointment_minutes, f.buffer_minutes, f.color, f.cycle_weeks, f.cycle_start]).toEqual([30, 0, '#2563eb', 1, null])
  })
  it('summarizes a weekly row', () => {
    expect(summarize({ configured: false })).toBe('Not set up')
    expect(summarize({ configured: true, appointment_minutes: 30, buffer_minutes: 10, windows })).toBe(
      '30 min · 10 min down-time · Mon, Wed',
    )
  })
  it('lists seven weekdays starting Monday like the server', () => {
    expect(WEEKDAYS.map((d) => d.value)).toEqual([0, 1, 2, 3, 4, 5, 6])
    expect(WEEKDAYS[0].label).toBe('Monday')
  })
})

describe('alternating weeks', () => {
  const windows = [
    { week: 0, weekday: 1, start_time: '13:00', end_time: '15:00' },
    { week: 1, weekday: 1, start_time: '18:00', end_time: '20:00' },
  ]
  const row = { windows, appointment_minutes: 30, buffer_minutes: 15, color: '#2563eb', cycle_weeks: 2, cycle_start: '2030-01-07' }
  const form = (over = {}) => ({ ...formFromAvailability(row), ...over })

  it('loads each week into its own list of days', () => {
    const f = formFromAvailability(row)
    expect(f.cycle_weeks).toBe(2)
    expect(f.cycle_start).toEqual(new Date(2030, 0, 7))
    expect(f.weeks[0][1].blocks).toEqual([{ start: '13:00', end: '15:00' }])
    expect(f.weeks[1][1].blocks).toEqual([{ start: '18:00', end: '20:00' }])
  })
  it('sends both weeks and the start date as a plain local date', () => {
    expect(buildAvailabilityPayload(form())).toEqual({
      appointment_minutes: 30, buffer_minutes: 15, color: '#2563eb', cycle_weeks: 2, cycle_start: '2030-01-07', windows,
    })
  })
  it('drops Week 2 hours when the schedule goes back to weekly', () => {
    const payload = buildAvailabilityPayload(form({ cycle_weeks: 1 }))
    expect(payload.windows.map((w) => w.week)).toEqual([0])
    expect(payload).not.toHaveProperty('cycle_start')
  })
  it('needs a start date for an alternating schedule', () => {
    expect(availabilityProblem(form({ cycle_start: null }))).toMatch(/Week 1 starts on/)
    expect(availabilityProblem(form())).toBe('')
  })
  it('names the week in a problem, and ignores Week 2 for a weekly schedule', () => {
    const weeks = form().weeks
    weeks[1][1].blocks[0] = { start: '20:00', end: '18:00' }
    expect(availabilityProblem(form({ weeks }))).toMatch(/^Week 2, Tuesday/)
    expect(availabilityProblem(form({ weeks, cycle_weeks: 1 }))).toBe('')
  })
  it('allows the same hours in both weeks', () => {
    const same = { ...row, windows: [windows[0], { ...windows[0], week: 1 }] }
    expect(availabilityProblem(formFromAvailability(same))).toBe('')
  })
  it('summarizes both weeks', () => {
    expect(summarize({ ...row, configured: true })).toBe('30 min · 15 min down-time · Week 1: Tue; Week 2: Tue')
    expect(summarize({ ...row, configured: true, windows: [windows[0]] })).toMatch(/Week 2: none/)
  })
})

describe('cycleWeekNumber', () => {
  const start = new Date(2030, 0, 7)       // a Monday
  it.each([
    [new Date(2030, 0, 7), 1], [new Date(2030, 0, 13), 1], [new Date(2030, 0, 14), 2],
    [new Date(2030, 0, 21), 1], [new Date(2029, 11, 31), 2], [new Date(2029, 11, 24), 1],
    [new Date(2031, 0, 6), 1],
  ])('%s is week %i', (day, week) => expect(cycleWeekNumber(day, start, 2)).toBe(week))
  it('counts from the Monday of the start date', () => {
    expect(cycleWeekNumber(new Date(2030, 0, 14), new Date(2030, 0, 10), 2)).toBe(2)
  })
  it('stays on Week 1 across the daylight saving change', () => {
    expect(cycleWeekNumber(new Date(2030, 2, 11), new Date(2030, 2, 4), 1)).toBe(1)
    expect(cycleWeekNumber(new Date(2030, 2, 18), new Date(2030, 2, 4), 2)).toBe(1)   // two weeks on, across the clock change
  })
  it('is always Week 1 for a weekly schedule or no start date', () => {
    expect(cycleWeekNumber(new Date(2030, 0, 14), start, 1)).toBe(1)
    expect(cycleWeekNumber(new Date(2030, 0, 14), null, 2)).toBe(1)
  })
})

describe('local date helpers', () => {
  it('parses a plain date without shifting the day', () => {
    expect(parseLocalDate('2030-01-07')).toEqual(new Date(2030, 0, 7))
  })
  it('finds the Monday of a week, including for a Sunday', () => {
    expect(toLocalISODate(mondayOf(new Date(2030, 0, 10)))).toBe('2030-01-07')
    expect(toLocalISODate(mondayOf(new Date(2030, 0, 13)))).toBe('2030-01-07')
    expect(toLocalISODate(mondayOf(new Date(2030, 0, 7)))).toBe('2030-01-07')
  })
})

describe('schedulingErrorMessage', () => {
  it('explains known codes and falls back to the server message', () => {
    expect(schedulingErrorMessage({ code: 'slot_unavailable' })).toMatch(/just taken/)
    expect(schedulingErrorMessage({ code: 'other', message: 'Nope' })).toBe('Nope')
    expect(schedulingErrorMessage(null)).toBe('Something went wrong.')
  })
})

describe('time off', () => {
  const navigators = [
    { tech_id: 1, first_name: 'Pat', last_name: 'Lee' }, { tech_id: 2, first_name: 'Sam', last_name: 'Ray' },
  ]
  const everyone = { time_off_id: 5, start_date: '2030-12-25', end_date: '2030-12-25', description: 'Christmas', all_navigators: true, tech_ids: [] }
  const some = { time_off_id: 6, start_date: '2030-01-07', end_date: '2030-01-11', description: 'Vacation', all_navigators: false, tech_ids: [2] }

  describe('addDaysISO', () => {
    it.each([
      ['2030-01-31', 1, '2030-02-01'], ['2030-12-31', 1, '2031-01-01'], ['2030-03-10', 1, '2030-03-11'],
      ['2030-03-01', -1, '2030-02-28'], ['2032-02-28', 1, '2032-02-29'], ['2030-01-07', 0, '2030-01-07'],
    ])('%s + %i = %s', (iso, n, expected) => expect(addDaysISO(iso, n)).toBe(expected))
  })

  it('formats one day and a range', () => {
    expect(formatDateRange('2030-12-25', '2030-12-25')).toBe('Dec 25, 2030')
    expect(formatDateRange('2030-01-07', '2030-01-11')).toBe('Jan 7, 2030 to Jan 11, 2030')
  })

  it('says who a block applies to', () => {
    expect(timeOffWho(everyone, navigators)).toBe('All navigators')
    expect(timeOffWho(some, navigators)).toBe('Sam Ray')
    expect(timeOffWho({ ...some, tech_ids: [2, 1, 9] }, navigators)).toBe('Sam Ray, Pat Lee, Navigator 9')
  })

  describe('timeOffEvents', () => {
    it('makes a labelled all-day bar and a shaded background, ending the day after (exclusive)', () => {
      const [bar, shade] = timeOffEvents([some], navigators)
      expect(bar).toMatchObject({
        id: 'off-6', title: 'Closed: Vacation (Sam Ray)', start: '2030-01-07', end: '2030-01-12', allDay: true, editable: false,
      })
      expect(bar.extendedProps.kind).toBe('time_off')
      expect(shade).toMatchObject({ id: 'off-bg-6', display: 'background', start: '2030-01-07', end: '2030-01-12' })
    })
    it('leaves the navigator names out when it applies to everyone', () => {
      expect(timeOffEvents([everyone], navigators)[0].title).toBe('Closed: Christmas')
    })
    it('crosses a month end', () => {
      expect(timeOffEvents([{ ...everyone, start_date: '2030-12-31', end_date: '2030-12-31' }], navigators)[0].end).toBe('2031-01-01')
    })
    it('is empty for no blocks', () => expect(timeOffEvents([], navigators)).toEqual([]))
  })

  describe('form', () => {
    const form = (over = {}) => ({ ...emptyTimeOffForm(), dates: [new Date(2030, 11, 25), null], description: 'Christmas', ...over })
    it('starts as everyone with nothing filled in', () => {
      expect(emptyTimeOffForm()).toEqual({ dates: null, all: true, tech_ids: [], description: '' })
    })
    it('accepts a single day, with no second date picked', () => expect(timeOffProblem(form())).toBe(''))
    it('accepts a range and specific navigators', () => {
      expect(timeOffProblem(form({ dates: [new Date(2030, 0, 7), new Date(2030, 0, 11)], all: false, tech_ids: [1] }))).toBe('')
    })
    it.each([
      [{ dates: null }, /Pick a day/], [{ dates: [] }, /Pick a day/],
      [{ dates: [new Date(2030, 0, 11), new Date(2030, 0, 7)] }, /can't be before/],
      [{ dates: [new Date(2030, 0, 1), new Date(2031, 5, 1)] }, /one year/],
      [{ description: '   ' }, /description/], [{ description: 'x'.repeat(201) }, /200/],
      [{ all: false, tech_ids: [] }, /at least one navigator/],
    ])('rejects %j', (over, message) => expect(timeOffProblem(form(over))).toMatch(message))

    it('sends one day as the same start and end, using local dates', () => {
      expect(buildTimeOffPayload(form({ dates: [new Date(2030, 11, 25, 23, 30), null] }))).toEqual({
        start_date: '2030-12-25', end_date: '2030-12-25', description: 'Christmas', all_navigators: true, tech_ids: [],
      })
    })
    it('sends a range with chosen navigators, and drops them when "all" is on', () => {
      const range = [new Date(2030, 0, 7), new Date(2030, 0, 11)]
      expect(buildTimeOffPayload(form({ dates: range, all: false, tech_ids: [2], description: ' Vacation ' }))).toEqual({
        start_date: '2030-01-07', end_date: '2030-01-11', description: 'Vacation', all_navigators: false, tech_ids: [2],
      })
      expect(buildTimeOffPayload(form({ dates: range, all: true, tech_ids: [2] })).tech_ids).toEqual([])
    })
    it('loads a block back into the form', () => {
      expect(formFromTimeOff(everyone).dates).toEqual([new Date(2030, 11, 25), null])
      const f = formFromTimeOff(some)
      expect(f.dates).toEqual([new Date(2030, 0, 7), new Date(2030, 0, 11)])
      expect([f.all, f.tech_ids, f.description]).toEqual([false, [2], 'Vacation'])
      expect(f.tech_ids).not.toBe(some.tech_ids)    // a copy, so editing doesn't change the list on screen
    })
  })

  describe('affectedMessage', () => {
    it('is empty when nothing is affected', () => expect(affectedMessage(0)).toBe(''))
    it('uses the right wording for one and for many', () => {
      expect(affectedMessage(1)).toMatch(/^1 booked appointment is already/)
      expect(affectedMessage(3)).toMatch(/^3 booked appointments are already/)
      expect(affectedMessage(3)).toMatch(/Nothing was changed/)
    })
  })
})