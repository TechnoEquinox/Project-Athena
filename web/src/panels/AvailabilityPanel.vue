<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import DatePicker from 'primevue/datepicker'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import Message from 'primevue/message'
import SelectButton from 'primevue/selectbutton'
import TimeOffSection from './TimeOffSection.vue'
import { listAvailability, saveAvailability } from '../schedulingApi'
import {
  availabilityProblem, buildAvailabilityPayload, CYCLE_OPTIONS, cycleWeekNumber, DEFAULT_COLORS,
  formFromAvailability, mondayOf, navigatorName, schedulingErrorMessage, summarize,
} from '../lib/scheduling'

const rows = ref([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

const edit = ref({ open: false, row: null, form: null, busy: false, error: '', week: 0 })

const alternating = computed(() => edit.value.form?.cycle_weeks === 2)
const weekOptions = [{ label: 'Week 1', value: 0 }, { label: 'Week 2', value: 1 }]

// The days being edited: Week 1's unless the admin has switched to Week 2 of an alternating schedule.
const activeDays = computed(() => edit.value.form?.weeks[alternating.value ? edit.value.week : 0] ?? [])
const thisWeek = computed(() => {
  const f = edit.value.form
  return f && alternating.value && f.cycle_start ? cycleWeekNumber(new Date(), f.cycle_start, 2) : null
})

function onCycleChange(weeks) {
  const form = edit.value.form
  edit.value.week = 0
  // Offer this week's Monday as a starting point the first time alternating weeks are turned on.
  if (weeks === 2 && !form.cycle_start) form.cycle_start = mondayOf(new Date())
}

async function load() {
  loading.value = true
  try {
    rows.value = await listAvailability()
  } catch (err) {
    error.value = schedulingErrorMessage(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function open(row) {
  // New navigators get the next color nobody else is using.
  const used = new Set(rows.value.map((r) => r.color).filter(Boolean))
  const free = DEFAULT_COLORS.find((c) => !used.has(c)) ?? DEFAULT_COLORS[0]
  edit.value = { open: true, row, form: formFromAvailability(row, free), busy: false, error: '', week: 0 }
}

function addBlock(day) {
  day.blocks.push({ start: '09:00', end: '12:00' })
}

async function save() {
  const problem = availabilityProblem(edit.value.form)
  if (problem) {
    edit.value.error = problem
    return
  }
  edit.value.busy = true
  edit.value.error = ''
  try {
    await saveAvailability(edit.value.row.tech_id, buildAvailabilityPayload(edit.value.form))
    notice.value = `Saved availability for ${navigatorName(edit.value.row)}.`
    edit.value.open = false
    await load()
  } catch (err) {
    edit.value.error = schedulingErrorMessage(err)
  } finally {
    edit.value.busy = false
  }
}
</script>

<template>
  <h3>Navigator Availability</h3>
  <p class="muted">
    Set when each Digital Navigator takes appointments, how long a standard appointment is, and the
    down-time kept between appointments. Times are the library's local time. Booking offers only the
    open slots this produces.
  </p>
  <Message v-if="notice" severity="success" :closable="false" class="mb">{{ notice }}</Message>
  <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

  <DataTable :value="rows" :loading="loading" data-key="tech_id">
    <Column header="Navigator">
      <template #body="{ data }">
        <span class="swatch" :style="{ background: data.color ?? '#d1d5db' }" />{{ navigatorName(data) }}
      </template>
    </Column>
    <Column header="Availability">
      <template #body="{ data }">{{ summarize(data) }}</template>
    </Column>
    <Column header="">
      <template #body="{ data }">
        <Button :label="data.configured ? 'Edit' : 'Set up'" size="small" @click="open(data)" />
      </template>
    </Column>
  </DataTable>

  <Dialog v-model:visible="edit.open" modal :header="edit.row ? navigatorName(edit.row) : ''" :style="{ width: '36rem' }">
    <template v-if="edit.form">
      <div class="grid">
        <label for="av-min">Appointment length (minutes)</label>
        <InputNumber v-model="edit.form.appointment_minutes" input-id="av-min" :min="5" :max="240" show-buttons />
        <label for="av-buf">Down-time between appointments (minutes)</label>
        <InputNumber v-model="edit.form.buffer_minutes" input-id="av-buf" :min="0" :max="120" show-buttons />
        <label for="av-color">Calendar color</label>
        <input id="av-color" v-model="edit.form.color" type="color" class="color" />
      </div>

      <h4>Schedule</h4>
      <SelectButton
        v-model="edit.form.cycle_weeks" :options="CYCLE_OPTIONS" option-label="label" option-value="value"
        :allow-empty="false" aria-label="How the schedule repeats" @update:model-value="onCycleChange"
      />
      <div v-if="alternating" class="cycle">
        <div class="grid">
          <label for="av-start">Week 1 starts on</label>
          <DatePicker v-model="edit.form.cycle_start" input-id="av-start" date-format="mm/dd/yy" show-icon />
        </div>
        <p class="muted">
          Weeks run Monday to Sunday and alternate from that week on.
          <template v-if="thisWeek"> This week is <strong>Week {{ thisWeek }}</strong>.</template>
        </p>
        <SelectButton
          v-model="edit.week" :options="weekOptions" option-label="label" option-value="value"
          :allow-empty="false" aria-label="Which week to edit"
        />
      </div>

      <h4>{{ alternating ? `Hours for Week ${edit.week + 1}` : 'Weekly hours' }}</h4>
      <div v-for="day in activeDays" :key="`${edit.week}-${day.weekday}`" class="day">
        <label class="daylabel">
          <Checkbox v-model="day.enabled" binary :input-id="`day-${day.weekday}`" @update:model-value="(on) => on && !day.blocks.length && addBlock(day)" />
          {{ day.label }}
        </label>
        <div v-if="day.enabled" class="blocks">
          <div v-for="(b, i) in day.blocks" :key="i" class="block">
            <input v-model="b.start" type="time" :aria-label="`${day.label} start ${i + 1}`" />
            to
            <input v-model="b.end" type="time" :aria-label="`${day.label} end ${i + 1}`" />
            <Button icon="pi pi-times" text severity="secondary" :aria-label="`Remove block ${i + 1} on ${day.label}`" @click="day.blocks.splice(i, 1)" />
          </div>
          <Button label="Add block" text size="small" @click="addBlock(day)" />
        </div>
      </div>
      <Message v-if="edit.error" severity="error" :closable="false">{{ edit.error }}</Message>
    </template>
    <template #footer>
      <Button label="Cancel" text severity="secondary" :disabled="edit.busy" @click="edit.open = false" />
      <Button label="Save" :loading="edit.busy" @click="save" />
    </template>
  </Dialog>
  <TimeOffSection :techs="rows" />
</template>

<style scoped>
.swatch { display: inline-block; width: 0.75rem; height: 0.75rem; border-radius: 2px; margin-right: 0.5rem; }
.grid { display: grid; grid-template-columns: 1fr auto; gap: 0.75rem 1rem; align-items: center; }
.color { width: 3rem; height: 2rem; padding: 0; }
.cycle { margin-top: 0.75rem; }
.day { display: flex; gap: 1rem; padding: 0.4rem 0; border-top: 1px solid #e5e7eb; }
.daylabel { width: 9rem; display: flex; align-items: center; gap: 0.5rem; }
.blocks { display: flex; flex-direction: column; gap: 0.25rem; }
.block { display: flex; align-items: center; gap: 0.5rem; }
</style>