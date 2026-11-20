// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import { useJobRunner } from './jobRunner'

function reply(status, body) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) })
}

const ID = 'a'.repeat(32)
let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
  setCsrf('tok')
})

const noWait = () => Promise.resolve()

/** Answer the request for a job first, then each check in turn. */
function script(...answers) {
  fetchMock.mockReturnValueOnce(reply(202, { job: { id: ID, action: 'backup', state: 'queued' } }))
  for (const a of answers) fetchMock.mockReturnValueOnce(a)
}
const running = (log = '') => reply(200, { job: { id: ID, action: 'backup', state: 'running' }, log })
const done = (state = 'succeeded', log = 'all good') => reply(200, { job: { id: ID, action: 'backup', state }, log })

async function settle(runner, times = 20) {
  for (let i = 0; i < times && runner.active.value; i += 1) await Promise.resolve()
  await new Promise((r) => setTimeout(r, 0))
}

describe('job runner', () => {
  it('starts a job, follows it, and reports when it finishes', async () => {
    const finished = vi.fn()
    const runner = useJobRunner({ sleep: noWait, onFinished: finished })
    script(running('step 1'), running('step 2'), done())
    const queued = await runner.start('backup')
    expect(queued.id).toBe(ID)
    expect(runner.active.value).toBe(true)
    await vi.waitFor(() => expect(finished).toHaveBeenCalledTimes(1))
    expect(runner.active.value).toBe(false)
    expect(runner.job.value.state).toBe('succeeded')
    expect(runner.log.value).toBe('all good')
    expect(fetchMock.mock.calls[1][0]).toBe(`/api/admin/server/jobs/${ID}`)
  })

  it('passes the password and code to the server', async () => {
    const runner = useJobRunner({ sleep: noWait })
    script(done())
    await runner.start('reboot', { current_password: 'pw', code: '123456' })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      action: 'reboot', current_password: 'pw', code: '123456',
    })
  })

  it('throws a refusal to the caller and does not start following anything', async () => {
    const runner = useJobRunner({ sleep: noWait })
    fetchMock.mockReturnValueOnce(reply(409, { error: 'job_in_progress' }))
    await expect(runner.start('backup')).rejects.toMatchObject({ code: 'job_in_progress' })
    expect(runner.active.value).toBe(false)
    expect(runner.job.value).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('keeps going through short outages, such as while Athena restarts', async () => {
    const finished = vi.fn()
    const runner = useJobRunner({ sleep: noWait, onFinished: finished })
    script(
      Promise.reject(new TypeError('network')), reply(502, {}), reply(404, { error: 'not_found' }),
      done(),
    )
    await runner.start('restart-services')
    await vi.waitFor(() => expect(finished).toHaveBeenCalled())
    expect(runner.job.value.state).toBe('succeeded')
    expect(runner.lostContact.value).toBe(false)
  })

  it('shows lost contact while checks are failing', async () => {
    const runner = useJobRunner({ sleep: noWait, maxFailures: 1000 })
    fetchMock.mockReturnValueOnce(reply(202, { job: { id: ID, action: 'backup', state: 'queued' } }))
    fetchMock.mockReturnValue(Promise.reject(new TypeError('network')))
    await runner.start('backup')
    await vi.waitFor(() => expect(runner.lostContact.value).toBe(true))
    runner.stop()
  })

  it('gives up after too many failures in a row', async () => {
    const finished = vi.fn()
    const runner = useJobRunner({ sleep: noWait, maxFailures: 3, onFinished: finished })
    fetchMock.mockReturnValueOnce(reply(202, { job: { id: ID, action: 'backup', state: 'queued' } }))
    fetchMock.mockReturnValue(Promise.reject(new TypeError('network')))
    await runner.start('backup')
    await vi.waitFor(() => expect(runner.active.value).toBe(false))
    expect(finished).not.toHaveBeenCalled()
    expect(runner.lostContact.value).toBe(true)
  })

  it('reports a failed job as finished', async () => {
    const finished = vi.fn()
    const runner = useJobRunner({ sleep: noWait, onFinished: finished })
    script(done('failed', 'boom'))
    await runner.start('backup')
    await vi.waitFor(() => expect(finished).toHaveBeenCalled())
    expect(runner.job.value.state).toBe('failed')
  })

  it('stops checking when dismissed or stopped', async () => {
    const runner = useJobRunner({ sleep: () => new Promise((r) => setTimeout(r, 5)) })
    script(running(), running(), running(), running())
    await runner.start('backup')
    runner.dismiss()
    expect(runner.job.value).toBeNull()
    expect(runner.active.value).toBe(false)
    await settle(runner)
    const calls = fetchMock.mock.calls.length
    await new Promise((r) => setTimeout(r, 40))
    expect(fetchMock.mock.calls.length).toBe(calls)
  })

  it('a newer job replaces an older one', async () => {
    const runner = useJobRunner({ sleep: () => new Promise((r) => setTimeout(r, 5)) })
    script(running(), running())
    await runner.start('backup')
    fetchMock.mockReset()
    fetchMock.mockReturnValueOnce(reply(202, { job: { id: 'b'.repeat(32), action: 'check-updates', state: 'queued' } }))
    fetchMock.mockReturnValue(reply(200, { job: { id: 'b'.repeat(32), action: 'check-updates', state: 'succeeded' }, log: 'x' }))
    await runner.start('check-updates')
    await vi.waitFor(() => expect(runner.active.value).toBe(false))
    expect(runner.job.value.id).toBe('b'.repeat(32))
    for (const call of fetchMock.mock.calls.slice(1)) expect(call[0]).toContain('b'.repeat(32))
  })
})
