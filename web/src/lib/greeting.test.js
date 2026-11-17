// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { describe, expect, it } from 'vitest'
import { greeting } from './greeting'

describe('greeting', () => {
  const at = (hour, minute = 0) => new Date(2026, 10, 14, hour, minute)

  it.each([
    [5, 0, 'Good Morning, sally'],
    [9, 30, 'Good Morning, sally'],
    [11, 59, 'Good Morning, sally'],
    [12, 0, 'Good Afternoon, sally'],
    [16, 59, 'Good Afternoon, sally'],
    [17, 0, 'Good Evening, sally'],
    [23, 59, 'Good Evening, sally'],
    [0, 0, 'Good Evening, sally'],
    [4, 59, 'Good Evening, sally'],
  ])('at %i:%i says %s', (hour, minute, expected) => {
    expect(greeting(at(hour, minute), 'sally')).toBe(expected)
  })

  it('leaves the name off when there is none', () => {
    expect(greeting(at(9), '')).toBe('Good Morning')
    expect(greeting(at(9), undefined)).toBe('Good Morning')
  })
})