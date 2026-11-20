// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { ref } from 'vue'
import { isFinished } from './lib/server'
import { getJob, requestJob } from './serverApi'

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Starts one server job and follows it until it finishes.
 *
 * Restarting Athena briefly takes the web app offline, so a failed check while a job
 * is running is normal: it is retried, and only many failures in a row give up.
 */
export function useJobRunner({ interval = 2000, maxFailures = 45, onFinished = () => {}, sleep = wait } = {}) {
  const job = ref(null)
  const log = ref('')
  const active = ref(false)
  const lostContact = ref(false)
  let token = 0

  async function poll(mine, id) {
    let failures = 0
    while (mine === token) {
      await sleep(interval)
      if (mine !== token) return
      try {
        const data = await getJob(id)
        if (mine !== token) return
        failures = 0
        lostContact.value = false
        job.value = data.job
        log.value = data.log
        if (isFinished(data.job.state)) {
          active.value = false
          onFinished(data.job)
          return
        }
      } catch {
        failures += 1
        lostContact.value = true
        if (failures >= maxFailures) {
          active.value = false
          return
        }
      }
    }
  }

  /** Ask for the job. A refusal (wrong password, another job running) is thrown to the caller. */
  async function start(action, check = {}) {
    const { job: queued } = await requestJob(action, check)
    const mine = ++token
    job.value = queued
    log.value = ''
    active.value = true
    lostContact.value = false
    poll(mine, queued.id)
    return queued
  }

  function dismiss() {
    token += 1
    active.value = false
    job.value = null
    log.value = ''
    lostContact.value = false
  }

  /** Stop checking (the page is going away). */
  function stop() {
    token += 1
  }

  return { job, log, active, lostContact, start, dismiss, stop }
}
