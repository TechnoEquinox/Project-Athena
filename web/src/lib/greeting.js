// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

export function greeting(now, name) {
  const hour = now.getHours()
  const part = hour >= 5 && hour < 12 ? 'Morning' : hour >= 12 && hour < 17 ? 'Afternoon' : 'Evening'
  return name ? `Good ${part}, ${name}` : `Good ${part}`
}