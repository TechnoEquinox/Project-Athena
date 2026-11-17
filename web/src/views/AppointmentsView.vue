<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import DatePicker from 'primevue/datepicker'
import Message from 'primevue/message'
import Select from 'primevue/select'
import AppointmentFormDialog from '../components/AppointmentFormDialog.vue'
import { formatDateTime, techLabel } from '../lib/appointments'
import { listLocations } from '../locationsApi'
import { useAppointments } from '../stores/appointments'
import { useAuth } from '../stores/auth'
import { listTechs } from '../techsApi'

const auth = useAuth()
const store = useAppointments()
const route = useRoute()
const router = useRouter()

const range = ref(store.range)
const techs = ref([])
const locations = ref([])
const showCreate = ref(false)

onMounted(async () => {
  store.load()
  const [t, l] = await Promise.all([
    listTechs({ includeInactive: true }).catch(() => []),
    listLocations({ includeInactive: true }).catch(() => []),
  ])
    techs.value = t.map((x) => ({ tech_id: x.tech_id, label: techLabel(x) }))
  locations.value = l
})

function onRange(value) {
  range.value = value
  // A range is only applied once both ends are picked, or when it is cleared
  if (value === null || (value[0] && value[1])) {
    store.setRange(value)
    store.load()
  }
}

function onTech(id) {
  store.setTech(id ?? null)
  store.load()
}

function onLocation(id) {
  store.setLocation(id ?? null)
  store.load()
}

function onPage(event) {
  store.setPage(event.first)
  store.load()
}

function saved(appointment) {
  router.push({ name: 'appointment', params: { id: appointment.appointment_id } })
}
</script>

<template>
  <div class="toolbar">
    <h2 class="grow">Appointments</h2>
    <Button v-if="auth.canWrite" label="Log appointment" @click="showCreate = true" />
  </div>

  <Message v-if="route.query.deleted" severity="success" :closable="false" class="mb">
    Appointment deleted.
  </Message>

  <div class="filters">
    <DatePicker
      :model-value="range"
      selection-mode="range"
      show-button-bar
      show-icon
      :manual-input="false"
      placeholder="Date range"
      @update:model-value="onRange"
    />
    <Select
      :model-value="store.techId"
      :options="techs"
      option-label="label"
      option-value="tech_id"
      placeholder="All techs"
      show-clear
      @update:model-value="onTech"
    />
    <Select
      :model-value="store.locationId"
      :options="locations"
      option-label="name"
      option-value="location_id"
      placeholder="All locations"
      show-clear
      @update:model-value="onLocation"
    />
  </div>

  <Message v-if="store.error" severity="error" :closable="false" class="mb">{{ store.error }}</Message>

  <DataTable
    :value="store.rows"
    lazy
    paginator
    :rows="store.limit"
    :total-records="store.total"
    :first="store.first"
    :loading="store.loading"
    :always-show-paginator="store.total > store.limit"
    data-key="appointment_id"
    @page="onPage"
  >
    <Column header="When">
      <template #body="{ data }">
        <router-link :to="{ name: 'appointment', params: { id: data.appointment_id } }">
          {{ formatDateTime(data.appointment_at) }}
        </router-link>
      </template>
    </Column>
    <Column header="Client">
      <template #body="{ data }">
        <router-link :to="{ name: 'client', params: { id: data.client.client_id } }">
          {{ data.client.last_name }}, {{ data.client.first_name }}
        </router-link>
      </template>
    </Column>
    <Column header="Tech">
      <template #body="{ data }">{{ data.tech.first_name }} {{ data.tech.last_name }}</template>
    </Column>
    <Column header="Location">
      <template #body="{ data }">{{ data.location?.name ?? '' }}</template>
    </Column>
    <Column header="Length">
      <template #body="{ data }">{{ data.length_minutes }} min</template>
    </Column>
    <template #empty>No appointments match these filters.</template>
  </DataTable>
  <p class="muted">{{ store.total }} appointment{{ store.total === 1 ? '' : 's' }}</p>

  <AppointmentFormDialog v-model:visible="showCreate" @saved="saved" />
</template>