// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { colorAt } from './charts'

// ---------- formatting ----------

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB']

export function formatBytes(bytes) {
  if (bytes == null || Number.isNaN(bytes)) return '—'
  let value = bytes
  let i = 0
  while (value >= 1024 && i < UNITS.length - 1) {
    value /= 1024
    i += 1
  }
  const digits = i === 0 || value >= 100 ? 0 : 1
  return `${value.toFixed(digits)} ${UNITS[i]}`
}

export function formatUptime(seconds) {
  if (seconds == null) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days} day${days === 1 ? '' : 's'}, ${hours} hr`
  if (hours > 0) return `${hours} hr, ${minutes} min`
  return `${minutes} min`
}

export const formatPercent = (value) => (value == null ? '—' : `${Math.round(value)}%`)

/** How full something is: green under 70%, amber under 90%, red above. */
export function usageSeverity(percent) {
  if (percent == null) return 'secondary'
  if (percent >= 90) return 'danger'
  if (percent >= 70) return 'warn'
  return 'success'
}

/** "just now", "5 min ago", "3 hr ago", "2 days ago" from a Unix time in seconds. */
export function ageText(unixSeconds, nowMs = Date.now()) {
  if (!unixSeconds) return 'never'
  const s = Math.max(0, Math.round(nowMs / 1000 - unixSeconds))
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} hr ago`
  const days = Math.floor(s / 86400)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

// ---------- the agent ----------

/** What to tell the admin about the server agent, from the /health response. */
export function agentStatus(response) {
  if (!response || response.agent === 'unavailable') {
    return {
      label: 'Not responding',
      severity: 'danger',
      detail: 'The server agent has not reported yet. It may not be installed or running.',
    }
  }
  if (response.agent === 'stale') {
    return {
      label: 'Out of date',
      severity: 'warn',
      detail: `The last report was ${ageText(response.health?.generated_at)}. The agent may have stopped.`,
    }
  }
  return { label: 'Running', severity: 'success', detail: '' }
}

const CONTAINER_NAMES = { api: 'Athena', db: 'Database', caddy: 'Web server' }

/** One row per Athena container, with a plain name and a good/bad flag. */
export function containerRows(containers) {
  if (!Array.isArray(containers)) return []
  return containers
    .map((c) => {
      const part = String(c.name).split('-').slice(1, -1).join('-') || c.name
      const running = c.state === 'running' && !/unhealthy|starting/i.test(c.status || '')
      return {
        key: c.name,
        name: CONTAINER_NAMES[part] ?? part,
        status: c.status || c.state,
        ok: running,
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name))
}

// ---------- charts ----------

const HOURS = [
  { label: '1 hour', value: 1 },
  { label: '6 hours', value: 6 },
  { label: '24 hours', value: 24 },
]
export const HISTORY_RANGES = HOURS

const MAX_POINTS = 144

/** Keep the chart readable: at most MAX_POINTS evenly spread points, always including the newest. */
export function thin(points, max = MAX_POINTS) {
  if (points.length <= max) return points
  const step = points.length / max
  const out = []
  for (let i = 0; i < max; i += 1) out.push(points[Math.floor(i * step)])
  out[out.length - 1] = points[points.length - 1]
  return out
}

const clock = (unixSeconds) =>
  new Date(unixSeconds * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

export const historyEmpty = (points) => !Array.isArray(points) || points.length < 2

export function usageChart(points) {
  const shown = thin(points)
  const line = (label, key, i) => ({
    label,
    data: shown.map((p) => p[key]),
    borderColor: colorAt(i),
    backgroundColor: colorAt(i),
    tension: 0.2,
    pointRadius: 0,
    borderWidth: 2,
  })
  return {
    labels: shown.map((p) => clock(p.t)),
    datasets: [line('Processor', 'cpu', 0), line('Memory', 'mem', 1)],
  }
}

export const usageOptions = () => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false,   // the page refreshes itself, so no redrawing flourish every 15 seconds
  interaction: { mode: 'index', intersect: false },
  plugins: { legend: { display: true, position: 'bottom' } },
  scales: {
    y: { min: 0, max: 100, ticks: { callback: (v) => `${v}%` }, title: { display: true, text: 'Used' } },
    x: { ticks: { maxTicksLimit: 8, autoSkip: true } },
  },
})

export const diskEmpty = (disk) => !disk || !disk.total

export function diskChart(disk, backupsBytes = 0, filesBytes = 0, databaseBytes = 0) {
  // Each slice is capped by what is left of the used space, so the pieces never add up to more than the disk.
  let left = Math.max(disk.used, 0)
  const take = (bytes) => {
    const part = Math.min(Math.max(bytes || 0, 0), left)
    left -= part
    return part
  }
  const backups = take(backupsBytes)
  const files = take(filesBytes)
  const database = take(databaseBytes)
  return {
    labels: ['Athena backups', 'Athena files', 'Athena database', 'Everything else', 'Free'],
    datasets: [{
      data: [backups, files, database, left, disk.free],
      backgroundColor: [colorAt(1), colorAt(2), colorAt(4), colorAt(0), '#d1d5db'],
    }],
  }
}

export const diskOptions = () => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  plugins: {
    legend: { position: 'right' },
    tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${formatBytes(ctx.parsed)}` } },
  },
})

// ---------- errors ----------

const MESSAGES = {
  agent_unavailable: 'The server agent is not running, so this server cannot be managed from here yet.',
  job_in_progress: 'Another job is still running. Wait for it to finish, then try again.',
  current_password_incorrect: 'That password is not correct.',
  invalid_code: 'That code is not correct.',
}

export function serverErrorMessage(err) {
  return MESSAGES[err?.code] ?? err?.message ?? 'Something went wrong.'
}

// ---------- jobs ----------

// Which actions exist, and which ones make the admin type their password again first.
export const JOB_ACTIONS = {
  backup: { label: 'Back up now', reauth: false },
  'check-updates': { label: 'Check for updates', reauth: false },
  'apply-updates': { label: 'Install Ubuntu updates', reauth: true },
  'restart-services': { label: 'Restart Athena', reauth: true },
  'docker-cleanup': { label: 'Clean up unused Docker files', reauth: false },
  reboot: { label: 'Restart the server', reauth: true },
}

export const needsReauth = (action) => JOB_ACTIONS[action]?.reauth === true
export const actionLabel = (action) => JOB_ACTIONS[action]?.label ?? String(action ?? '')

const FINISHED = ['succeeded', 'failed', 'refused']
export const isFinished = (state) => FINISHED.includes(state)

export function jobState(state) {
  switch (state) {
    case 'queued': return { label: 'Waiting', severity: 'info' }
    case 'running': return { label: 'Running', severity: 'info' }
    case 'succeeded': return { label: 'Done', severity: 'success' }
    case 'failed': return { label: 'Failed', severity: 'danger' }
    case 'refused': return { label: 'Refused', severity: 'danger' }
    default: return { label: String(state ?? ''), severity: 'secondary' }
  }
}

/** The password (and 2FA code, if the admin has 2FA) for the actions that ask for them. */
export function buildCheck(password, second = '', recovery = false) {
  const check = { current_password: password }
  const value = second.trim()
  if (value) check[recovery ? 'recovery_code' : 'code'] = value
  return check
}

/** What the admin should be told after a job ends. */
export function jobOutcome(job) {
  if (!job) return ''
  if (job.state === 'succeeded' && job.action === 'reboot') {
    return 'The server is restarting. This page will work again in a minute or two. Reload it when you can.'
  }
  if (job.state === 'succeeded') return job.message || 'Done.'
  if (job.state === 'failed' || job.state === 'refused') return job.message || 'It did not finish.'
  return ''
}

// ---------- backups ----------

const DAY_S = 86400

/** Seconds since an ISO time like 2026-11-19T15:27:04Z, or null. */
function isoAgeSeconds(iso, nowMs) {
  const t = Date.parse(iso ?? '')
  return Number.isNaN(t) ? null : Math.max(0, Math.round((nowMs - t) / 1000))
}

export const isoAgeText = (iso, nowMs = Date.now()) => {
  const s = isoAgeSeconds(iso, nowMs)
  return s == null ? 'never' : ageText(Math.round(nowMs / 1000) - s, nowMs)
}

/** One plain sentence each for the newest backup and for the USB copy, with a colour. */
export function backupSummary(backups, nowMs = Date.now()) {
  if (!backups || !backups.status || Object.keys(backups.status).length === 0) {
    return {
      last: { text: 'No backup has run yet.', severity: 'warn' },
      usb: { text: 'No USB backup drive has been used yet.', severity: 'secondary' },
    }
  }
  const s = backups.status
  let last
  const age = isoAgeSeconds(s.last_success, nowMs)
  if (s.ok === false) {
    last = { text: `The last backup failed: ${s.message || 'unknown reason'}`, severity: 'danger' }
  } else if (age == null) {
    last = { text: 'No successful backup yet.', severity: 'warn' }
  } else if (age > 36 * 3600) {
    last = { text: `Last backup ${isoAgeText(s.last_success, nowMs)}. That is more than a day ago.`, severity: 'warn' }
  } else {
    last = { text: `Last backup ${isoAgeText(s.last_success, nowMs)}.`, severity: 'success' }
  }

  let usb
  const usbAge = isoAgeSeconds(s.usb_last_success, nowMs)
  if (!backups.usb_drives) {
    usb = { text: 'No USB backup drive is set up. Run "sudo athena usb-setup" on the server.', severity: 'warn' }
  } else if (usbAge == null) {
    usb = { text: 'A USB drive is set up, but no backup has been copied to it yet.', severity: 'warn' }
  } else if (usbAge > 7 * DAY_S) {
    usb = { text: `Last USB copy ${isoAgeText(s.usb_last_success, nowMs)}. Plug the drive in.`, severity: 'warn' }
  } else {
    usb = { text: `Last USB copy ${isoAgeText(s.usb_last_success, nowMs)}.`, severity: 'success' }
  }
  return { last, usb }
}

/** The time in a backup's file name (it is in UTC), as a Date, or null. */
export function backupFileWhen(name) {
  const m = /^athena-backup-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})\.tar\.age$/.exec(name ?? '')
  if (!m) return null
  const [y, mo, d, h, mi, s] = m.slice(1).map(Number)
  return new Date(Date.UTC(y, mo - 1, d, h, mi, s))
}

export function backupRows(backups, limit = 8) {
  return (backups?.files ?? []).slice(0, limit).map((f) => ({
    name: f.name,
    when: backupFileWhen(f.name),
    bytes: f.bytes,
  }))
}

// ---------- updates ----------

export function updatesSummary(updates, nowMs = Date.now()) {
  if (!updates) return { text: 'Not checked yet.', severity: 'secondary', count: null }
  const checked = ageText(updates.checked_at, nowMs)
  if (updates.count === 0) return { text: `Everything is up to date (checked ${checked}).`, severity: 'success', count: 0 }
  return {
    text: `${updates.count} update${updates.count === 1 ? '' : 's'} waiting (checked ${checked}).`,
    severity: 'warn',
    count: updates.count,
  }
}

export function packageRows(updates, limit = 8) {
  const all = updates?.packages ?? []
  return { shown: all.slice(0, limit), hidden: Math.max(0, (updates?.count ?? all.length) - limit) }
}
