// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { describe, expect, it } from 'vitest'
import { ApiError } from '../api'
import {
  HISTORY_RANGES, JOB_ACTIONS, actionLabel, agentStatus, ageText, backupFileWhen, backupRows, backupSummary,
  buildCheck, containerRows, diskChart, diskEmpty, diskOptions, formatBytes, formatPercent, formatUptime, historyEmpty,
  isFinished, isoAgeText, jobOutcome, jobState, needsReauth, packageRows, serverErrorMessage, thin,
  updatesSummary, usageChart, usageOptions, usageSeverity,
} from './server'

describe('formatBytes', () => {
  it('uses the right unit', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1023)).toBe('1023 B')
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(709376)).toBe('693 KB')
    expect(formatBytes(5 * 1024 ** 3)).toBe('5.0 GB')
    expect(formatBytes(105089261568)).toBe('97.9 GB')
  })
  it('copes with missing values', () => {
    expect(formatBytes(null)).toBe('—')
    expect(formatBytes(undefined)).toBe('—')
    expect(formatBytes(NaN)).toBe('—')
  })
})

describe('formatUptime', () => {
  it('shows days, hours or minutes', () => {
    expect(formatUptime(237662)).toBe('2 days, 18 hr')
    expect(formatUptime(86400)).toBe('1 day, 0 hr')
    expect(formatUptime(3 * 3600 + 120)).toBe('3 hr, 2 min')
    expect(formatUptime(125)).toBe('2 min')
    expect(formatUptime(null)).toBe('—')
  })
})

describe('formatPercent and usageSeverity', () => {
  it('rounds and handles nothing', () => {
    expect(formatPercent(36.3)).toBe('36%')
    expect(formatPercent(null)).toBe('—')
  })
  it('colours by how full', () => {
    expect(usageSeverity(10)).toBe('success')
    expect(usageSeverity(69.9)).toBe('success')
    expect(usageSeverity(70)).toBe('warn')
    expect(usageSeverity(89.9)).toBe('warn')
    expect(usageSeverity(90)).toBe('danger')
    expect(usageSeverity(null)).toBe('secondary')
  })
})

describe('ageText', () => {
  const now = 1_000_000 * 1000
  it('describes how long ago', () => {
    expect(ageText(1_000_000 - 5, now)).toBe('just now')
    expect(ageText(1_000_000 - 300, now)).toBe('5 min ago')
    expect(ageText(1_000_000 - 7200, now)).toBe('2 hr ago')
    expect(ageText(1_000_000 - 86400, now)).toBe('1 day ago')
    expect(ageText(1_000_000 - 3 * 86400, now)).toBe('3 days ago')
  })
  it('never goes negative and handles nothing', () => {
    expect(ageText(1_000_000 + 50, now)).toBe('just now')
    expect(ageText(null, now)).toBe('never')
    expect(ageText(0, now)).toBe('never')
  })
})

describe('agentStatus', () => {
  it('is running when the report is fresh', () => {
    expect(agentStatus({ agent: 'ok', health: {} }).severity).toBe('success')
  })
  it('warns when the report is old', () => {
    const s = agentStatus({ agent: 'stale', health: { generated_at: 1 } })
    expect(s.severity).toBe('warn')
    expect(s.detail).toMatch(/stopped/)
  })
  it('is an error when there is no report', () => {
    expect(agentStatus({ agent: 'unavailable' }).severity).toBe('danger')
    expect(agentStatus(null).severity).toBe('danger')
  })
})

describe('containerRows', () => {
  it('gives plain names and flags problems', () => {
    const rows = containerRows([
      { name: 'athena-caddy-1', state: 'running', status: 'Up 8 minutes' },
      { name: 'athena-db-1', state: 'running', status: 'Up 8 minutes (healthy)' },
      { name: 'athena-api-1', state: 'restarting', status: 'Restarting (1) 3 seconds ago' },
    ])
    expect(rows.map((r) => [r.name, r.ok])).toEqual([
      ['Athena', false], ['Database', true], ['Web server', true],
    ])
  })
  it('treats unhealthy and still-starting as problems', () => {
    const rows = containerRows([
      { name: 'athena-db-1', state: 'running', status: 'Up 1 second (health: starting)' },
      { name: 'athena-api-1', state: 'running', status: 'Up 1 minute (unhealthy)' },
    ])
    expect(rows.every((r) => r.ok === false)).toBe(true)
  })
  it('copes with missing data', () => {
    expect(containerRows(null)).toEqual([])
    expect(containerRows(undefined)).toEqual([])
  })
})

describe('usage chart', () => {
  const pts = (n) => Array.from({ length: n }, (_, i) => ({ t: 1_700_000_000 + i * 60, cpu: i % 100, mem: 40 }))
  it('needs at least two points', () => {
    expect(historyEmpty([])).toBe(true)
    expect(historyEmpty(pts(1))).toBe(true)
    expect(historyEmpty(pts(2))).toBe(false)
    expect(historyEmpty(null)).toBe(true)
  })
  it('has a line for processor and one for memory', () => {
    const chart = usageChart(pts(5))
    expect(chart.labels).toHaveLength(5)
    expect(chart.datasets.map((d) => d.label)).toEqual(['Processor', 'Memory'])
    expect(chart.datasets[0].data).toEqual([0, 1, 2, 3, 4])
    expect(chart.datasets[1].data).toEqual([40, 40, 40, 40, 40])
  })
  it('thins out a long history but keeps the newest point', () => {
    const all = pts(1440)
    const small = thin(all, 144)
    expect(small).toHaveLength(144)
    expect(small[0]).toBe(all[0])
    expect(small[small.length - 1]).toBe(all[all.length - 1])
    expect(thin(pts(10), 144)).toHaveLength(10)
  })
  it('does not animate, because the page refreshes itself', () => {
    expect(usageOptions().animation).toBe(false)
    expect(diskOptions().animation).toBe(false)
  })
  it('keeps the scale at 0 to 100 per cent', () => {
    const o = usageOptions()
    expect(o.scales.y.min).toBe(0)
    expect(o.scales.y.max).toBe(100)
  })
  it('offers 1, 6 and 24 hours', () => {
    expect(HISTORY_RANGES.map((r) => r.value)).toEqual([1, 6, 24])
  })
})

describe('disk chart', () => {
  const disk = { total: 100, used: 40, free: 60 }
  it('splits used space into backups and everything else', () => {
    const c = diskChart(disk, 10)
    expect(c.labels).toEqual(['Athena backups', 'Everything else', 'Free'])
    expect(c.datasets[0].data).toEqual([10, 30, 60])
  })
  it('never lets backups exceed the used space', () => {
    expect(diskChart(disk, 500).datasets[0].data).toEqual([40, 0, 60])
    expect(diskChart(disk, null).datasets[0].data).toEqual([0, 40, 60])
  })
  it('knows when there is nothing to draw', () => {
    expect(diskEmpty(null)).toBe(true)
    expect(diskEmpty({ total: 0 })).toBe(true)
    expect(diskEmpty(disk)).toBe(false)
  })
})

describe('serverErrorMessage', () => {
  it('explains the known errors', () => {
    expect(serverErrorMessage(new ApiError(503, { error: 'agent_unavailable' }))).toMatch(/not running/)
    expect(serverErrorMessage(new ApiError(409, { error: 'job_in_progress' }))).toMatch(/still running/)
  })
  it('falls back to the server message', () => {
    expect(serverErrorMessage(new ApiError(400, { error: 'x', message: 'Plain words' }))).toBe('Plain words')
    expect(serverErrorMessage(null)).toBe('Something went wrong.')
  })
})
describe('which actions ask for the password again', () => {
  it('asks for the risky ones only', () => {
    for (const a of ['apply-updates', 'restart-services', 'reboot']) expect(needsReauth(a)).toBe(true)
    for (const a of ['backup', 'check-updates', 'docker-cleanup']) expect(needsReauth(a)).toBe(false)
    expect(needsReauth('format-disk')).toBe(false)
  })
  it('has a plain label for every action', () => {
    for (const key of Object.keys(JOB_ACTIONS)) expect(actionLabel(key)).toBeTruthy()
    expect(actionLabel('mystery')).toBe('mystery')
    expect(actionLabel(undefined)).toBe('')
  })
})

describe('job states', () => {
  it('knows when a job is over', () => {
    expect(['succeeded', 'failed', 'refused'].every(isFinished)).toBe(true)
    expect(['queued', 'running', undefined].some(isFinished)).toBe(false)
  })
  it('labels and colours each state', () => {
    expect(jobState('running')).toEqual({ label: 'Running', severity: 'info' })
    expect(jobState('succeeded').severity).toBe('success')
    expect(jobState('failed').severity).toBe('danger')
    expect(jobState('refused').severity).toBe('danger')
    expect(jobState('weird').label).toBe('weird')
  })
  it('explains how a job ended', () => {
    expect(jobOutcome(null)).toBe('')
    expect(jobOutcome({ state: 'running' })).toBe('')
    expect(jobOutcome({ state: 'succeeded', action: 'backup', message: 'Done.' })).toBe('Done.')
    expect(jobOutcome({ state: 'succeeded', action: 'reboot' })).toMatch(/restarting/)
    expect(jobOutcome({ state: 'failed', message: 'A step failed.' })).toBe('A step failed.')
    expect(jobOutcome({ state: 'failed' })).toMatch(/did not finish/)
  })
})

describe('buildCheck', () => {
  it('sends a code, a recovery code, or just the password', () => {
    expect(buildCheck('pw', ' 123456 ')).toEqual({ current_password: 'pw', code: '123456' })
    expect(buildCheck('pw', 'abcd-efgh', true)).toEqual({ current_password: 'pw', recovery_code: 'abcd-efgh' })
    expect(buildCheck('pw')).toEqual({ current_password: 'pw' })
    expect(buildCheck('pw', '   ')).toEqual({ current_password: 'pw' })
  })
  it('leaves the password exactly as typed', () => {
    expect(buildCheck(' spaced pw ').current_password).toBe(' spaced pw ')
  })
})

describe('backupSummary', () => {
  const now = Date.parse('2026-11-20T12:00:00Z')
  const good = {
    status: { ok: true, last_success: '2026-11-20T02:45:00Z', usb_last_success: '2026-11-19T15:27:04Z' },
    usb_drives: 1,
  }
  it('is happy when both are recent', () => {
    const s = backupSummary(good, now)
    expect(s.last).toEqual({ text: 'Last backup 9 hr ago.', severity: 'success' })
    expect(s.usb.severity).toBe('success')
  })
  it('warns when nothing has run', () => {
    expect(backupSummary(null, now).last.severity).toBe('warn')
    expect(backupSummary({ status: {} }, now).last.severity).toBe('warn')
  })
  it('shows a failure in red with the reason', () => {
    const s = backupSummary({ ...good, status: { ...good.status, ok: false, message: 'Disk full' } }, now)
    expect(s.last.severity).toBe('danger')
    expect(s.last.text).toMatch(/Disk full/)
  })
  it('warns when the last backup is over a day and a half old', () => {
    const old = { ...good, status: { ...good.status, last_success: '2026-11-18T02:45:00Z' } }
    expect(backupSummary(old, now).last.severity).toBe('warn')
  })
  it('explains the USB state', () => {
    expect(backupSummary({ ...good, usb_drives: 0 }, now).usb.text).toMatch(/usb-setup/)
    expect(backupSummary({ ...good, status: { ok: true, last_success: good.status.last_success } }, now).usb.text)
      .toMatch(/not been copied|no backup has been copied/i)
    const stale = { ...good, status: { ...good.status, usb_last_success: '2026-11-01T00:00:00Z' } }
    expect(backupSummary(stale, now).usb.severity).toBe('warn')
  })
})

describe('backup files', () => {
  it('reads the time from the file name as UTC', () => {
    expect(backupFileWhen('athena-backup-20261119-152700.tar.age').toISOString()).toBe('2026-11-19T15:27:00.000Z')
    expect(backupFileWhen('notes.txt')).toBeNull()
    expect(backupFileWhen(undefined)).toBeNull()
  })
  it('lists the newest rows up to a limit', () => {
    const files = Array.from({ length: 12 }, (_, i) => ({
      name: `athena-backup-202611${String(20 - i).padStart(2, '0')}-024500.tar.age`, bytes: 1000 + i,
    }))
    const rows = backupRows({ files }, 8)
    expect(rows).toHaveLength(8)
    expect(rows[0].bytes).toBe(1000)
    expect(backupRows(null)).toEqual([])
  })
  it('says never for a missing time', () => {
    expect(isoAgeText(undefined)).toBe('never')
    expect(isoAgeText('garbage')).toBe('never')
  })
})

describe('updates', () => {
  const now = 1_000_000 * 1000
  it('summarises the three situations', () => {
    expect(updatesSummary(null).count).toBeNull()
    expect(updatesSummary({ count: 0, checked_at: 1_000_000 - 60 }, now).severity).toBe('success')
    const some = updatesSummary({ count: 1, checked_at: 1_000_000 - 7200 }, now)
    expect(some).toMatchObject({ severity: 'warn', count: 1 })
    expect(some.text).toBe('1 update waiting (checked 2 hr ago).')
    expect(updatesSummary({ count: 11, checked_at: 1_000_000 }, now).text).toMatch(/^11 updates/)
  })
  it('shows a few packages and counts the rest', () => {
    const packages = Array.from({ length: 11 }, (_, i) => ({ name: `p${i}`, to: '1' }))
    const rows = packageRows({ count: 11, packages }, 8)
    expect(rows.shown).toHaveLength(8)
    expect(rows.hidden).toBe(3)
    expect(packageRows(null)).toEqual({ shown: [], hidden: 0 })
  })
})
