<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { onMounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import SelectButton from 'primevue/selectbutton'
import Tag from 'primevue/tag'
import { adminErrorMessage, restoreSeverity, restoreWindowText, statusText } from '../lib/admin'
import { formatDateTime } from '../lib/appointments'
import { callerName, statusSeverity } from '../lib/calls'
import { listDeleted, restoreAppointment, restoreCall, restoreClient } from '../restoreApi'

const kinds = [
  { label: 'Clients', value: 'clients' },
  { label: 'Appointments', value: 'appointments' },
  { label: 'Calls', value: 'calls' },
]
const idKey = { clients: 'client_id', appointments: 'appointment_id', calls: 'call_id' }

const kind = ref('clients')
const rows = ref([])
const retentionDays = ref(30)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const restoredLink = ref(null)
const busyId = ref(null)

let sequence = 0
async function load() {
  const mine = ++sequence
  loading.value = true
  try {
    const data = await listDeleted(kind.value)
    if (mine !== sequence) return
    rows.value = data.items
    retentionDays.value = data.retentionDays
  } catch (err) {
    if (mine === sequence) error.value = adminErrorMessage(err)
  } finally {
    if (mine === sequence) loading.value = false
  }
}

onMounted(load)
watch(kind, () => {
  rows.value = []
  error.value = ''
  notice.value = ''
  restoredLink.value = null
  load()
})

const dup = ref({ open: false, row: null, matches: [], busy: false, error: '' })

function clientRestoredNotice(row, data) {
  const r = data.restored ?? {}
  return (
    `Restored ${row.last_name}, ${row.first_name}. Also restored: ` +
    `${r.devices ?? 0} device(s), ${r.appointments ?? 0} appointment(s), ${r.call_logs ?? 0} call(s).`
  )
}

async function restore(row) {
  error.value = ''
  notice.value = ''
  restoredLink.value = null
  const id = row[idKey[kind.value]]
  busyId.value = id
  try {
    if (kind.value === 'clients') {
      const data = await restoreClient(id)
      notice.value = clientRestoredNotice(row, data)
      restoredLink.value = { name: 'client', params: { id } }
    } else if (kind.value === 'appointments') {
      await restoreAppointment(id)
      notice.value = 'Appointment restored.'
      restoredLink.value = { name: 'appointment', params: { id } }
    } else {
      await restoreCall(id)
      notice.value = 'Call restored.'
    }
    await load()
  } catch (err) {
    if (err.code === 'possible_duplicate') {
      dup.value = { open: true, row, matches: err.body.matches ?? [], busy: false, error: '' }
    } else {
      error.value = adminErrorMessage(err)
      if (err.code === 'retention_expired' || err.code === 'not_found') await load()
    }
  } finally {
    busyId.value = null
  }
}

async function restoreAnyway() {
  const row = dup.value.row
  dup.value.busy = true
  dup.value.error = ''
  try {
    const data = await restoreClient(row.client_id, { force: true })
    dup.value.open = false
    notice.value = clientRestoredNotice(row, data)
    restoredLink.value = { name: 'client', params: { id: row.client_id } }
    await load()
  } catch (err) {
    dup.value.error = adminErrorMessage(err)
  } finally {
    dup.value.busy = false
  }
}
</script>

<template>
  <h3>Restore deleted records</h3>
  <p class="muted">
    Deleted records can be restored for {{ retentionDays }} days. After that they are permanently removed.
    Appointments and calls of a deleted client come back with the client, so they aren't listed separately.
  </p>

  <Message v-if="notice" severity="success" :closable="false" class="mb">
    {{ notice }}
    <router-link v-if="restoredLink" :to="restoredLink">View it</router-link>
  </Message>
  <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

  <SelectButton
    v-model="kind"
    :options="kinds"
    option-label="label"
    option-value="value"
    :allow-empty="false"
    class="mb"
    aria-label="Record type"
  />

  <DataTable :value="rows" :loading="loading" :data-key="idKey[kind]">
    <template v-if="kind === 'clients'">
      <Column header="Client">
        <template #body="{ data }">{{ data.last_name }}, {{ data.first_name }}</template>
      </Column>
    </template>
    <template v-else-if="kind === 'appointments'">
      <Column header="Appointment">
        <template #body="{ data }">{{ formatDateTime(data.appointment_at) }}</template>
      </Column>
      <Column header="Client">
        <template #body="{ data }">{{ data.client.last_name }}, {{ data.client.first_name }}</template>
      </Column>
      <Column header="Tech">
        <template #body="{ data }">{{ data.tech.first_name }} {{ data.tech.last_name }}</template>
      </Column>
    </template>
    <template v-else>
      <Column header="Received">
        <template #body="{ data }">{{ formatDateTime(data.called_at) }}</template>
      </Column>
      <Column header="Caller">
        <template #body="{ data }">{{ callerName(data) }}</template>
      </Column>
      <Column header="Status">
        <template #body="{ data }">
          <Tag :value="statusText(data.status)" :severity="statusSeverity(data.status)" />
        </template>
      </Column>
    </template>
    <Column header="Deleted">
      <template #body="{ data }">{{ formatDateTime(data.deleted_at) }}</template>
    </Column>
    <Column header="Time left">
      <template #body="{ data }">
        <Tag :value="restoreWindowText(data.restorable_until)" :severity="restoreSeverity(data.restorable_until)" />
      </template>
    </Column>
    <Column header="" style="width: 8rem">
      <template #body="{ data }">
        <Button label="Restore" size="small" :loading="busyId === data[idKey[kind]]" @click="restore(data)" />
      </template>
    </Column>
    <template #empty>Nothing deleted in the last {{ retentionDays }} days.</template>
  </DataTable>

  <Dialog v-model:visible="dup.open" modal header="Possible duplicate" :style="{ width: '28rem' }">
    <Message v-if="dup.error" severity="error" :closable="false" class="mb">{{ dup.error }}</Message>
    <p>An active client with the same name and phone already exists:</p>
    <ul>
      <li v-for="m in dup.matches" :key="m.client_id">
        <router-link :to="{ name: 'client', params: { id: m.client_id } }" @click="dup.open = false">
          {{ m.last_name }}, {{ m.first_name }}
        </router-link>
      </li>
    </ul>
    <p class="muted">Restoring anyway will give you two records for this person.</p>
    <template #footer>
      <Button label="Cancel" text severity="secondary" :disabled="dup.busy" @click="dup.open = false" />
      <Button label="Restore anyway" severity="warn" :loading="dup.busy" @click="restoreAnyway" />
    </template>
  </Dialog>
</template>