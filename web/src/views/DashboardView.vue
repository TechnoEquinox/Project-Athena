<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, onMounted, ref } from 'vue'
import Card from 'primevue/card'
import Chart from 'primevue/chart'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import ChartCard from '../components/ChartCard.vue'
import DashboardControls from '../components/DashboardControls.vue'
import { counterCards } from '../lib/dashboard'
import { greeting } from '../lib/greeting'
import {
  appointmentRows, appointmentsChart, appointmentsEmpty, axisOptions, callRows, callsChart,
  callsEmpty, devicesChart, devicesEmpty, formatMinutes, locationsChart, locationsEmpty,
  paceChart, pieOptions, languageSummary, languagesChart, languagesEmpty, languagesHeight, 
  languagesOptions, topLanguages,
} from '../lib/charts'
import { downloadReport } from '../statsApi'
import { useDashboard } from '../stores/dashboard'
import ConnecticutMap from '../components/ConnecticutMap.vue'
import { listCalls } from '../callsApi'
import { useAuth } from '../stores/auth'

const store = useDashboard()
const perTech = computed(() => store.mode === 'tech')
const exporting = ref('')
const exportError = ref('')

const auth = useAuth()
const greetingText = greeting(new Date(), auth.user?.username)
const waiting = ref(null)

onMounted(async () => {
  store.init()
  try {
    waiting.value = (await listCalls({ open: true, limit: 1, offset: 0 })).total
  } catch {
    waiting.value = null   // not worth an error on the home page
  }
})

const cards = computed(() => counterCards(store.counters))

const apptEmpty = computed(() => appointmentsEmpty(store.appointments))
const callEmpty = computed(() => callsEmpty(store.calls))
const locEmpty = computed(() => locationsEmpty(store.locations))
const devEmpty = computed(() => devicesEmpty(store.devices))
const zipsEmpty = computed(() => !store.zips || store.zips.total_clients === 0)

const countOptions = computed(() => axisOptions({ legend: perTech.value, integer: true }))
const paceOptions = computed(() => axisOptions({ legend: perTech.value, yTitle: 'Minutes' }))
const locationOptions = axisOptions({ legend: true, integer: true })

const apptData = computed(() => (apptEmpty.value ? null : appointmentsChart(store.appointments, store.mode)))
const paceData = computed(() => (apptEmpty.value ? null : paceChart(store.appointments, store.mode)))
const inboundData = computed(() => (callEmpty.value ? null : callsChart(store.calls, 'inbound', store.mode)))
const outboundData = computed(() => (callEmpty.value ? null : callsChart(store.calls, 'outbound', store.mode)))
const locationData = computed(() => (locEmpty.value ? null : locationsChart(store.locations)))
const deviceData = computed(() => (devEmpty.value ? null : devicesChart(store.devices)))

const languageOptions = languagesOptions()
const langEmpty = computed(() => languagesEmpty(store.languages))
const languageData = computed(() => (langEmpty.value ? null : languagesChart(store.languages)))
const langSummary = computed(() => (langEmpty.value ? null : languageSummary(store.languages)))
const langHidden = computed(() => (langEmpty.value ? 0 : topLanguages(store.languages).hidden))
const langHeight = computed(() =>
  langEmpty.value ? 12 : languagesHeight(Math.min(store.languages.languages.length, 12)),
)

async function exportReport(report) {
  exportError.value = ''
  exporting.value = report
  try {
    await downloadReport(report, { from: store.from, to: store.to, interval: store.interval })
  } catch (err) {
    exportError.value = err.message
  } finally {
    exporting.value = ''
  }
}
</script>

<template>
  <h2>{{ greetingText }}</h2>
  <p v-if="waiting" class="waiting">
    <router-link :to="{ name: 'calls' }">
      {{ waiting }} call{{ waiting === 1 ? '' : 's' }} waiting for a response
    </router-link>
  </p>
  <p v-else-if="waiting === 0" class="waiting muted">No calls are waiting for a response.</p>
  <DashboardControls />

  <Message v-if="store.error" severity="error" :closable="false" class="mb">{{ store.error }}</Message>
  <Message v-if="store.countersError" severity="warn" :closable="false" class="mb">
    The counters could not be loaded: {{ store.countersError }}
  </Message>
  <Message v-if="exportError" severity="error" :closable="false" class="mb">{{ exportError }}</Message>

  <div class="counters">
    <Card v-for="c in cards" :key="c.key">
      <template #content>
        <div class="counter-title">{{ c.title }} <span class="muted">{{ c.period }}</span></div>
        <div class="counter-value">{{ c.value }}</div>
        <div class="muted">appointments</div>
      </template>
    </Card>
  </div>

  <div class="dash-grid">
    <ChartCard
      title="Appointments"
      :loading="store.loading"
      :empty="apptEmpty"
      empty-text="No appointments in this range."
      :exporting="exporting === 'appointments'"
      @export="exportReport('appointments')"
    >
      <div class="chart">
        <Chart
          type="bar"
          :data="apptData"
          :options="countOptions"
          :canvas-props="{ role: 'img', 'aria-label': 'Bar chart of appointments per period' }"
        />
      </div>
      <DataTable v-if="perTech" :value="appointmentRows(store.appointments)" data-key="tech_id" class="sectop">
        <Column field="name" header="Navigator" />
        <Column field="count" header="Appointments" />
        <Column header="Average length">
          <template #body="{ data }">{{ formatMinutes(data.average) }}</template>
        </Column>
      </DataTable>
    </ChartCard>

    <ChartCard
      title="Average appointment length"
      :loading="store.loading"
      :empty="apptEmpty"
      empty-text="No appointments in this range."
      :exportable="false"
    >
      <p class="big">
        {{ formatMinutes(store.appointments.total.overall_average_minutes) }}
        <span class="muted">average over this range</span>
      </p>
      <div class="chart">
        <Chart
          type="line"
          :data="paceData"
          :options="paceOptions"
          :canvas-props="{ role: 'img', 'aria-label': 'Line chart of average appointment length per period' }"
        />
      </div>
      <p class="muted">The same numbers are in the appointments CSV.</p>
    </ChartCard>

    <ChartCard
      title="Calls"
      :loading="store.loading"
      :empty="callEmpty"
      empty-text="No calls in this range."
      :exporting="exporting === 'calls'"
      @export="exportReport('calls')"
    >
      <div class="chart-pair">
        <div>
          <h4>Inbound</h4>
          <div class="chart">
            <Chart
              type="bar"
              :data="inboundData"
              :options="countOptions"
              :canvas-props="{ role: 'img', 'aria-label': 'Bar chart of inbound calls per period' }"
            />
          </div>
        </div>
        <div>
          <h4>Outbound</h4>
          <div class="chart">
            <Chart
              type="bar"
              :data="outboundData"
              :options="countOptions"
              :canvas-props="{ role: 'img', 'aria-label': 'Bar chart of outbound calls per period' }"
            />
          </div>
        </div>
      </div>
      <DataTable v-if="perTech" :value="callRows(store.calls)" data-key="tech_id" class="sectop">
        <Column field="name" header="Navigator" />
        <Column field="inbound" header="Inbound" />
        <Column field="outbound" header="Outbound" />
      </DataTable>
    </ChartCard>

    <ChartCard
      title="Appointments by location"
      :loading="store.loading"
      :empty="locEmpty"
      empty-text="No appointments in this range."
      :exporting="exporting === 'locations'"
      @export="exportReport('locations')"
    >
      <div class="chart">
        <Chart
          type="line"
          :data="locationData"
          :options="locationOptions"
          :canvas-props="{ role: 'img', 'aria-label': 'Line chart of appointments per period, one line per location' }"
        />
      </div>
    </ChartCard>

    <ChartCard
      title="Devices seen"
      :loading="store.loading"
      :empty="devEmpty"
      empty-text="No devices were recorded in this range."
      :exporting="exporting === 'devices'"
      @export="exportReport('devices')"
    >
      <div class="chart">
        <Chart
          type="pie"
          :data="deviceData"
          :options="pieOptions()"
          :canvas-props="{ role: 'img', 'aria-label': 'Pie chart of device types seen' }"
        />
      </div>
      <p class="muted">
        {{ store.devices.total_devices }} device visit(s) across {{ store.devices.appointments }} appointment(s).
        {{ store.devices.appointments_without_devices }} appointment(s) had no device recorded.
      </p>
    </ChartCard>
    <ChartCard
      title="Languages spoken"
      :loading="store.loading"
      :empty="langEmpty"
      empty-text="No languages were recorded in this range."
      :exporting="exporting === 'languages'"
      @export="exportReport('languages')"
    >
      <div class="chart" :style="{ height: `${langHeight}rem` }">
        <Chart
          type="bar"
          :data="languageData"
          :options="languageOptions"
          :canvas-props="{ role: 'img', 'aria-label': 'Bar chart of the languages clients speak' }"
        />
      </div>
      <p class="muted">
        {{ langSummary.multilingual }} of {{ langSummary.total }} client(s) ({{ langSummary.multilingualPct }}%)
        speak more than one language. {{ langSummary.noLanguage }} have no language recorded.
        <span v-if="langHidden">The {{ langHidden }} least common language(s) are in the CSV.</span>
      </p>
    </ChartCard>
    <ChartCard
      class="wide"
      title="Where clients live"
      :loading="store.loading"
      :empty="zipsEmpty"
      empty-text="No clients had appointments in this range."
      :exporting="exporting === 'zips'"
      @export="exportReport('zips')"
    >
      <ConnecticutMap :report="store.zips" />
    </ChartCard>
  </div>
</template>