// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

export function debounce(fn, wait) {
    let timer = null
    const run = (...args) => {
        clearTimeout(timer)
        timer = setTimeout(() => {
            timer = null
            fn(...args)
        }, wait)
    }
    run.cancel = () => {
        clearTimeout(timer)
        timer = null
    }
    return run
}