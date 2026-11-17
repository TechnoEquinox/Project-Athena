// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { debounce } from './debounce'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('debounce', () => {
  it('waits for a quiet period', () => {
    const fn = vi.fn()
    const run = debounce(fn, 300)
    run('a')
    vi.advanceTimersByTime(299)
    expect(fn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(fn).toHaveBeenCalledWith('a')
  })

  it('calls once, with the last value', () => {
    const fn = vi.fn()
    const run = debounce(fn, 300)
    run('a')
    vi.advanceTimersByTime(200)
    run('ab')
    vi.advanceTimersByTime(200)
    run('abc')
    vi.advanceTimersByTime(300)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenCalledWith('abc')
  })

  it('can be cancelled', () => {
    const fn = vi.fn()
    const run = debounce(fn, 300)
    run('a')
    run.cancel()
    vi.advanceTimersByTime(1000)
    expect(fn).not.toHaveBeenCalled()
  })
})