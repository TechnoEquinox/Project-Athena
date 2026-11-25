<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import FullCalendar from '@fullcalendar/vue3'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import Button from 'primevue/button'
import Message from 'primevue/message'
import Select from 'primevue/select'
import BookingDialog from '../components/BookingDialog.vue'
import BookingDetailDialog from '../components/BookingDetailDialog.vue'
import { listBookings, listNavigators, listTimeOff } from '../schedulingApi'
import {
  colorMap, navigatorName, schedulingErrorMessage, timeOffEvents, toCalendarEvents, toLocalISODate,
} from '../lib/scheduling'
import { useAuth } from '../stores/auth'

const auth = useAuth()
const navigators = ref([])
const ALL = 'all'
const filter = ref(ALL)
const events = ref([])
const error = ref('')
const range = ref(null)

const booking = ref({ open: false, date: null })
const detail = ref({ open: false, id: null })

const filterOptions = computed(() => [
  { label: 'All navigators', value: ALL },
  ...navigators.value.map((n) => ({ label: navigatorName(n), value: n.tech_id })),
])

let sequence = 0
async function loadEvents() {
  if (!range.value) return
  const mine = ++sequence
  try {
    const techId = filter.value === ALL ? null : filter.value
    const [found, blocks] = await Promise.all([
      listBookings({ from: range.value.from, to: range.value.to, techId }),
      listTimeOff({ from: range.value.fromDay, to: range.value.toDay, techId }),
    ])
    if (mine === sequence) {
      events.value = [...toCalendarEvents(found, colorMap(navigators.value)), ...timeOffEvents(blocks, navigators.value)]
      error.value = ''
    }
  } catch (err) {
    if (mine === sequence) error.value = schedulingErrorMessage(err)
  }
}

onMounted(async () => {
  try {
    navigators.value = await listNavigators()
  } catch (err) {
    error.value = schedulingErrorMessage(err)
  }
  await loadEvents()
})
watch(filter, loadEvents)

const options = {
  plugins: [dayGridPlugin, timeGridPlugin, interactionPlugin],
  initialView: 'dayGridMonth',
  headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,timeGridDay' },
  height: 'auto',
  buttonIcons: false,
  buttonText: { prev: '‹ Prev', next: 'Next ›' },
  nowIndicator: true,
  eventTimeFormat: { hour: 'numeric', minute: '2-digit', meridiem: 'short' },
  datesSet: (info) => {
    range.value = {
      from: info.start.toISOString(), to: info.end.toISOString(),
      fromDay: toLocalISODate(info.start), toDay: toLocalISODate(info.end),
    }
    loadEvents()
  },
  eventClick: (info) => {
    if (info.event.extendedProps.kind === 'time_off') return
    detail.value = { open: true, id: Number(info.event.id) }
  },
  dateClick: (info) => {
    if (auth.canWrite) booking.value = { open: true, date: info.date }
  },
}
</script>

<template>
  <div class="head">
    <h2>Calendar</h2>
    <Select
      v-model="filter" :options="filterOptions" option-label="label" option-value="value"
      aria-label="Show navigator" class="filter"
    />
    <Button v-if="auth.canWrite" label="Book appointment" icon="pi pi-plus" @click="booking = { open: true, date: null }" />
  </div>

  <ul class="legend" aria-label="Navigator colors">
    <li v-for="n in navigators" :key="n.tech_id">
      <span class="swatch" :style="{ background: n.color }" />{{ navigatorName(n) }}
    </li>
  </ul>
  <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

  <FullCalendar :options="{ ...options, events }" />

  <BookingDialog
    v-model:visible="booking.open" :navigators="navigators" :initial-date="booking.date"
    :initial-tech-id="filter === ALL ? null : filter" @saved="loadEvents"
  />
  <BookingDetailDialog v-model:visible="detail.open" :booking-id="detail.id" @changed="loadEvents" />
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
.head h2 { margin: 0; margin-right: auto; }
.filter { min-width: 14rem; }
.legend { display: flex; gap: 1rem; flex-wrap: wrap; list-style: none; padding: 0; margin: 0 0 1rem; }
.swatch { display: inline-block; width: 0.75rem; height: 0.75rem; border-radius: 2px; margin-right: 0.4rem; }
:deep(.booking-cancelled), :deep(.booking-no_show) { opacity: 0.45; text-decoration: line-through; }
:deep(.booking-completed) { opacity: 0.7; }
:deep(.fc-event) { cursor: pointer; }
:deep(.time-off) { cursor: default; font-style: italic; }
:deep(.time-off-bg) { background: repeating-linear-gradient(45deg, #f3f4f6, #f3f4f6 8px, #e5e7eb 8px, #e5e7eb 16px); opacity: 0.8; }
</style>