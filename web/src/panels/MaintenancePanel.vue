<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Card from 'primevue/card'
import Chart from 'primevue/chart'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import SelectButton from 'primevue/selectbutton'
import Tag from 'primevue/tag'
import BackupsCard from '../components/BackupsCard.vue'
import ChartCard from '../components/ChartCard.vue'
import JobOutput from '../components/JobOutput.vue'
import PowerCard from '../components/PowerCard.vue'
import ReauthDialog from '../components/ReauthDialog.vue'
import UpdatesCard from '../components/UpdatesCard.vue'
import { useJobRunner } from '../jobRunner'
import {
  HISTORY_RANGES, actionLabel, agentStatus, ageText, containerRows, diskChart, diskEmpty, diskOptions, formatBytes,
  formatPercent, formatUptime, historyEmpty, jobState, needsReauth, serverErrorMessage, usageChart, usageOptions,
  usageSeverity,
} from '../lib/server'
import { getBackups, getHealth, getHistory, getUpdates, listJobs } from '../serverApi'
import { useAuth } from '../stores/auth'

const REFRESH_MS = 15000

const auth = useAuth()
const response = ref(null)
const backups = ref(null)
const updates = ref(null)
const jobs = ref([])
const serverBusy = ref(false)
const points = ref([])
const hours = ref(24)
const loading = ref(true)
const error = ref('')
let sequence = 0
let timer = null

async function load() {
  const mine = ++sequence
  try {
    // The extra pieces are nice to have: if one is missing, the rest still show.
    const soft = (promise) => promise.catch(() => undefined)
    const [h, hist, b, u, j] = await Promise.all([
      getHealth(), getHistory(hours.value), soft(getBackups()), soft(getUpdates()), soft(listJobs()),
    ])
    if (mine !== sequence) return
    response.value = h
    points.value = hist.points
    if (b !== undefined) backups.value = b
    if (u !== undefined) updates.value = u
    if (j !== undefined) {
      jobs.value = j.jobs
      serverBusy.value = j.busy
    }
    error.value = ''
  } catch (err) {
    if (mine === sequence) error.value = serverErrorMessage(err)
  } finally {
    if (mine === sequence) loading.value = false
  }
}

// ---------- running jobs ----------

const runner = useJobRunner({ onFinished: () => load() })
const jobCard = ref(null)

// The job box is at the top of the page. When a job starts, bring it into view.
watch(() => runner.job.value?.id, async (id) => {
  if (!id) return
  await nextTick()
  jobCard.value?.$el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
})
const busy = computed(() => runner.active.value || serverBusy.value)
const notice = ref('')

const ask = ref({ open: false, action: '', busy: false, error: '' })
const REAUTH_TEXT = {
  'apply-updates': 'Installing updates changes the server. Enter your password and code to continue.',
  'restart-services': 'Athena will be unavailable for about 30 seconds. Enter your password and code to continue.',
  reboot: 'The whole server will restart and Athena will be unavailable for a minute or two. Enter your password and code to continue.',
}

async function run(action) {
  notice.value = ''
  if (needsReauth(action)) {
    ask.value = { open: true, action, busy: false, error: '' }
    return
  }
  try {
    await runner.start(action)
    load()
  } catch (err) {
    notice.value = serverErrorMessage(err)
  }
}

async function confirmAsk(check) {
  ask.value.busy = true
  ask.value.error = ''
  try {
    await runner.start(ask.value.action, check)
    ask.value.open = false
    load()
  } catch (err) {
    ask.value.error = serverErrorMessage(err)
  } finally {
    ask.value.busy = false
  }
}

function tick() {
  if (!document.hidden) load()
}

onMounted(() => {
  load()
  timer = setInterval(tick, REFRESH_MS)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  sequence += 1   // ignore any answer still on its way
  runner.stop()
})
watch(hours, load)

const agent = computed(() => agentStatus(response.value))
const health = computed(() => response.value?.health ?? null)
const containers = computed(() => containerRows(health.value?.containers))
const tiles = computed(() => {
  const h = health.value
  if (!h) return []
  return [
    { key: 'cpu', title: 'Processor', value: formatPercent(h.cpu_percent), severity: usageSeverity(h.cpu_percent),
      note: `${h.cpu_count} core${h.cpu_count === 1 ? '' : 's'}, load ${h.load?.[0] ?? '—'}` },
    { key: 'mem', title: 'Memory', value: formatPercent(h.memory.percent), severity: usageSeverity(h.memory.percent),
      note: `${formatBytes(h.memory.used)} of ${formatBytes(h.memory.total)}` },
    { key: 'disk', title: 'Disk', value: formatPercent(h.disk.percent), severity: usageSeverity(h.disk.percent),
      note: `${formatBytes(h.disk.free)} free of ${formatBytes(h.disk.total)}` },
    { key: 'up', title: 'Running for', value: formatUptime(h.uptime_seconds), severity: 'secondary', small: true,
      note: `Last checked ${ageText(h.generated_at)}` },
  ]
})

const usageData = computed(() => (historyEmpty(points.value) ? null : usageChart(points.value)))
const diskData = computed(() => (!health.value || diskEmpty(health.value.disk)
    ? null : diskChart(health.value.disk, health.value.backups_bytes, health.value.athena_bytes, health.value.database_bytes)))
const usageOpts = usageOptions()
const diskOpts = diskOptions()
</script>

<template>
  <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>
  <Message v-if="notice" severity="error" :closable="false" class="mb">{{ notice }}</Message>

  <JobOutput v-if="runner.job.value" ref="jobCard" :job="runner.job.value" :log="runner.log.value" :active="runner.active.value"
             :lost-contact="runner.lostContact.value" @dismiss="runner.dismiss" />

  <Message v-else-if="serverBusy" severity="info" :closable="false" class="mb">
    The server is busy with another job. The buttons come back when it finishes.
  </Message>

  <ReauthDialog v-model:visible="ask.open" :title="actionLabel(ask.action)" :message="REAUTH_TEXT[ask.action] ?? ''"
                :confirm-label="actionLabel(ask.action)" :needs-code="!!auth.user?.two_factor_enabled"
                :busy="ask.busy" :error="ask.error" @confirm="confirmAsk" />

  <Message v-if="agent.severity !== 'success'" :severity="agent.severity === 'danger' ? 'error' : 'warn'"
           :closable="false" class="mb">
    <strong>Server agent: {{ agent.label }}.</strong> {{ agent.detail }}
  </Message>

  <Message v-if="health?.reboot_required" severity="warn" :closable="false" class="mb">
    The server needs a restart to finish installing updates.
  </Message>

  <p v-if="loading && !health" class="muted">Loading…</p>

  <template v-if="health">
    <div class="counters">
      <Card v-for="t in tiles" :key="t.key">
        <template #content>
          <div class="counter-title">{{ t.title }}</div>
          <div class="counter-value" :class="{ 'counter-value--small': t.small }">
            {{ t.value }}
            <Tag v-if="t.severity !== 'secondary'" :severity="t.severity"
                 :value="t.severity === 'success' ? 'OK' : t.severity === 'warn' ? 'High' : 'Very high'" />
          </div>
          <div class="muted">{{ t.note }}</div>
        </template>
      </Card>
    </div>

    <div class="dash-grid">
      <ChartCard title="Processor and memory" :exportable="false" :loading="loading"
                 :empty="!usageData" empty-text="Collecting data. Check back in a couple of minutes.">
        <div class="ctl-row">
          <SelectButton v-model="hours" :options="HISTORY_RANGES" option-label="label" option-value="value"
                        :allow-empty="false" aria-label="Time range" />
        </div>
        <div class="chart">
          <Chart type="line" :data="usageData" :options="usageOpts"
                 :canvas-props="{ role: 'img', 'aria-label': 'Line chart of processor and memory use over time' }" />
        </div>
      </ChartCard>

      <ChartCard title="Disk space" :exportable="false" :loading="loading"
                 :empty="!diskData" empty-text="Disk information is not available.">
        <div class="chart">
          <Chart type="pie" :data="diskData" :options="diskOpts"
                 :canvas-props="{ role: 'img', 'aria-label': 'Pie chart of used and free disk space' }" />
        </div>
      </ChartCard>

      <BackupsCard :backups="backups" :busy="busy" @run="run" />
      <UpdatesCard :updates="updates" :reboot-required="!!health.reboot_required" :busy="busy" @run="run" />
      <PowerCard :busy="busy" @run="run" />

      <Card>
        <template #title>This server</template>
        <template #content>
          <dl class="facts">
            <dt>Athena version</dt><dd>{{ health.athena_version || '—' }}</dd>
            <dt>Operating system</dt><dd>{{ health.os || '—' }}</dd>
            <dt>Kernel</dt><dd>{{ health.kernel || '—' }}</dd>
            <dt>Server name</dt><dd>{{ health.hostname || '—' }}</dd>
            <dt>Backups on this server</dt><dd>{{ formatBytes(health.backups_bytes) }}</dd>
            <dt>Ubuntu updates waiting</dt>
            <dd>{{ health.updates_pending == null ? 'Not checked yet' : health.updates_pending }}</dd>
          </dl>
          <h4 class="sectop">Athena services</h4>
          <p v-if="!containers.length" class="muted">No service information yet.</p>
          <ul v-else class="plain">
            <li v-for="c in containers" :key="c.key">
              <Tag :severity="c.ok ? 'success' : 'danger'" :value="c.ok ? 'Running' : 'Problem'" />
              {{ c.name }} <span class="muted">— {{ c.status }}</span>
            </li>
          </ul>
        </template>
      </Card>

      <Card class="wide">
        <template #title>Recent jobs</template>
        <template #content>
          <p v-if="!jobs.length" class="muted">Nothing has been run from this page yet.</p>
          <DataTable v-else :value="jobs" data-key="id" size="small">
            <Column header="What">
              <template #body="{ data }">{{ actionLabel(data.action) }}</template>
            </Column>
            <Column header="Started by">
              <template #body="{ data }">{{ data.requested_by || '—' }}</template>
            </Column>
            <Column header="When">
              <template #body="{ data }">{{ ageText(data.started_at) }}</template>
            </Column>
            <Column header="Result">
              <template #body="{ data }">
                <Tag :severity="jobState(data.state).severity" :value="jobState(data.state).label" />
              </template>
            </Column>
          </DataTable>
        </template>
      </Card>
    </div>
  </template>
</template>
