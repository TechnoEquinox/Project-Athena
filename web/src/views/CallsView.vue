<script setup>
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import DatePicker from 'primevue/datepicker'
import Message from 'primevue/message'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Tag from 'primevue/tag'
import CallFormDialog from '../components/CallFormDialog.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { deleteCall, listStatuses, updateCall } from '../callsApi'
import { formatDateTime, techLabel } from '../lib/appointments'
import { DONE_STATUS, callerName, isOpen, statusSeverity, waitingFor } from '../lib/calls'
import { formatPhone } from '../lib/forms'
import { useAuth } from '../stores/auth'
import { useCalls } from '../stores/calls'
import { listTechs } from '../techsApi'

const auth = useAuth()
const store = useCalls()

const modes = [
  { label: 'Callback queue', value: 'queue' },
  { label: 'All calls', value: 'all' },
]

const range = ref(store.range)
const statuses = ref([])
const techs = ref([])
const expanded = ref({})
const notice = ref('')
const rowError = ref('')
const busyId = ref(null)

const showForm = ref(false)
const editing = ref(null)
const confirm = ref({ open: false, call: null, busy: false, error: '' })

onMounted(async () => {
  store.load()
  const [s, t] = await Promise.all([
    listStatuses().catch(() => []),
    listTechs({ includeInactive: true }).catch(() => []),
  ])
  statuses.value = s
  techs.value = t.map((x) => ({ tech_id: x.tech_id, label: techLabel(x) }))
})

function reload() {
  store.load()
}

function onMode(value) {
  if (!value) return
  store.setMode(value)
  reload()
}

function onStatus(value) {
  store.setStatus(value ?? null)
  reload()
}

function onTech(value) {
  store.setTech(value ?? null)
  reload()
}

function onRange(value) {
  range.value = value
  // A range is only applied once both ends are picked, or when it is cleared
  if (value === null || (value[0] && value[1])) {
    store.setRange(value)
    reload()
  }
}

function onPage(event) {
  store.setPage(event.first)
  reload()
}

function openCreate() {
  editing.value = null
  showForm.value = true
}

function openEdit(call) {
  editing.value = call
  showForm.value = true
}

function onSaved() {
  notice.value = 'Call saved.'
  reload()
}

async function markDone(call) {
  rowError.value = ''
  notice.value = ''
  busyId.value = call.call_id
  try {
    await updateCall(call.call_id, { status: DONE_STATUS })
    notice.value = `Marked done: ${callerName(call)}.`
    reload()
  } catch (err) {
    rowError.value = err.message
  } finally {
    busyId.value = null
  }
}

function askDelete(call) {
  confirm.value = { open: true, call, busy: false, error: '' }
}

async function runDelete() {
  confirm.value.busy = true
  confirm.value.error = ''
  try {
    await deleteCall(confirm.value.call.call_id)
    confirm.value.open = false
    notice.value = 'Call deleted.'
    reload()
  } catch (err) {
    confirm.value.error = err.message
  } finally {
    confirm.value.busy = false
  }
}
</script>

<template>
  <div class="toolbar">
    <h2 class="grow">Calls</h2>
    <Button v-if="auth.canWrite" label="Log call" @click="openCreate" />
  </div>

  <Message v-if="notice" severity="success" :closable="false" class="mb">{{ notice }}</Message>
  <Message v-if="rowError" severity="error" :closable="false" class="mb">{{ rowError }}</Message>
  <Message v-if="store.error" severity="error" :closable="false" class="mb">{{ store.error }}</Message>

  <div class="filters">
    <SelectButton
      :model-value="store.mode"
      :options="modes"
      option-label="label"
      option-value="value"
      :allow-empty="false"
      aria-label="View"
      @update:model-value="onMode"
    />
    <template v-if="store.mode === 'all'">
      <Select
        :model-value="store.status"
        :options="statuses"
        option-label="label"
        option-value="value"
        placeholder="All statuses"
        show-clear
        @update:model-value="onStatus"
      />
      <DatePicker
        :model-value="range"
        selection-mode="range"
        show-button-bar
        show-icon
        :manual-input="false"
        placeholder="Date range"
        @update:model-value="onRange"
      />
    </template>
    <Select
      :model-value="store.techId"
      :options="techs"
      option-label="label"
      option-value="tech_id"
      placeholder="All techs"
      show-clear
      @update:model-value="onTech"
    />
  </div>

  <DataTable
    v-model:expanded-rows="expanded"
    :value="store.rows"
    lazy
    paginator
    :rows="store.limit"
    :total-records="store.total"
    :first="store.first"
    :loading="store.loading"
    :always-show-paginator="store.total > store.limit"
    data-key="call_id"
    @page="onPage"
  >
    <Column expander style="width: 3rem" />
    <Column header="Received">
      <template #body="{ data }">{{ formatDateTime(data.called_at) }}</template>
    </Column>
    <Column v-if="store.mode === 'queue'" header="Waiting">
      <template #body="{ data }">{{ waitingFor(data.called_at) }}</template>
    </Column>
    <Column header="Caller">
      <template #body="{ data }">
        <router-link v-if="data.client" :to="{ name: 'client', params: { id: data.client.client_id } }">
          {{ callerName(data) }}
        </router-link>
        <span v-else>{{ callerName(data) }}</span>
      </template>
    </Column>
    <Column header="Phone">
      <template #body="{ data }">{{ formatPhone(data.phone) }}</template>
    </Column>
    <Column header="Status">
      <template #body="{ data }">
        <Tag :value="data.status_label" :severity="statusSeverity(data.status)" />
      </template>
    </Column>
    <Column header="Tech">
      <template #body="{ data }">{{ data.tech ? `${data.tech.first_name} ${data.tech.last_name}` : '' }}</template>
    </Column>
    <Column v-if="auth.canWrite" header="" style="width: 17rem">
      <template #body="{ data }">
        <div class="row">
          <Button
            v-if="isOpen(data.status)"
            label="Done"
            size="small"
            severity="success"
            :loading="busyId === data.call_id"
            @click="markDone(data)"
          />
          <Button label="Edit" size="small" text @click="openEdit(data)" />
          <Button label="Delete" size="small" text severity="danger" @click="askDelete(data)" />
        </div>
      </template>
    </Column>
    <template #expansion="{ data }">
      <p class="notes">{{ data.notes || 'No notes.' }}</p>
    </template>
    <template #empty>
      {{ store.mode === 'queue' ? 'Nobody is waiting for a call back.' : 'No calls match these filters.' }}
    </template>
  </DataTable>
  <p class="muted">{{ store.total }} call{{ store.total === 1 ? '' : 's' }}</p>

  <CallFormDialog v-model:visible="showForm" :call="editing" @saved="onSaved" />
  <ConfirmDialog
    v-model:visible="confirm.open"
    title="Delete this call?"
    message="It will be hidden from lists and reports. An admin can restore it for a limited time."
    confirm-label="Delete call"
    :busy="confirm.busy"
    :error="confirm.error"
    @confirm="runDelete"
  />
</template>