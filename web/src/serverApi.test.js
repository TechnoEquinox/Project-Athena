// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import { getBackups, getHealth, getHistory, getJob, getUpdates, listJobs, requestJob } from './serverApi'

function reply(status, body) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
}

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
  setCsrf('tok')
})

const url = () => fetchMock.mock.calls[0][0]
const options = () => fetchMock.mock.calls[0][1]

describe('server API', () => {
  it('reads health', async () => {
    fetchMock.mockReturnValue(reply(200, { agent: 'ok', health: {} }))
    expect(await getHealth()).toEqual({ agent: 'ok', health: {} })
    expect(url()).toBe('/api/admin/server/health')
  })

  it('reads history for a number of hours', async () => {
    fetchMock.mockReturnValue(reply(200, { points: [] }))
    await getHistory(6)
    expect(url()).toBe('/api/admin/server/history?hours=6')
  })

  it('reads the waiting updates and unwraps them', async () => {
    fetchMock.mockReturnValue(reply(200, { updates: { count: 2 } }))
    expect(await getUpdates()).toEqual({ count: 2 })
    fetchMock.mockReturnValue(reply(200, { updates: null }))
    expect(await getUpdates()).toBeNull()
  })

  it('reads the backup list and unwraps it', async () => {
    fetchMock.mockReturnValue(reply(200, { backups: { files: [] } }))
    expect(await getBackups()).toEqual({ files: [] })
    expect(url()).toBe('/api/admin/server/backups')
    fetchMock.mockReturnValue(reply(200, { backups: null }))
    expect(await getBackups()).toBeNull()
  })

  it('lists jobs and reads one', async () => {
    fetchMock.mockReturnValue(reply(200, { jobs: [], busy: false }))
    await listJobs()
    expect(url()).toBe('/api/admin/server/jobs')
    fetchMock.mockClear()
    fetchMock.mockReturnValue(reply(200, { job: {}, log: '' }))
    await getJob('a'.repeat(32))
    expect(url()).toBe(`/api/admin/server/jobs/${'a'.repeat(32)}`)
  })

  it('asks for a job with only the action when nothing else is needed', async () => {
    fetchMock.mockReturnValue(reply(202, { job: { id: 'x', state: 'queued' } }))
    await requestJob('backup')
    expect(options().method).toBe('POST')
    expect(JSON.parse(options().body)).toEqual({ action: 'backup' })
    expect(options().headers['X-CSRF-Token']).toBe('tok')
  })

  it('sends the password and code along for actions that need them', async () => {
    fetchMock.mockReturnValue(reply(202, { job: {} }))
    await requestJob('reboot', { current_password: 'pw', code: '123456' })
    expect(JSON.parse(options().body)).toEqual({ action: 'reboot', current_password: 'pw', code: '123456' })
  })

  it('throws the server error', async () => {
    fetchMock.mockReturnValue(reply(409, { error: 'job_in_progress', message: 'busy' }))
    await expect(requestJob('backup')).rejects.toMatchObject({ status: 409, code: 'job_in_progress' })
  })
})