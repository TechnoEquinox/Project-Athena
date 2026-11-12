<script setup>
import { onMounted } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import Select from 'primevue/select'
import {
  AUDIT_ACTIONS, actorLabel, formatDetail, humanizeAction, targetLabel,
} from '../lib/admin'
import { formatDateTime } from '../lib/appointments'
import { useAudit } from '../stores/audit'

const store = useAudit()
const actions = AUDIT_ACTIONS.map((a) => ({ value: a, label: humanizeAction(a) }))

onMounted(() => store.load())

function onAction(value) {
  store.setAction(value ?? null)
  store.load()
}
</script>

<template>
  <div class="toolbar">
    <h3 class="grow">Audit log</h3>
    <Button label="Refresh" severity="secondary" size="small" :loading="store.loading" @click="store.load()" />
  </div>
  <p class="muted">
    Who did what and when, newest first. The log records which fields changed, never the patron's details,
    and entries can't be edited or deleted.
  </p>

  <div class="filters">
    <Select
      :model-value="store.action"
      :options="actions"
      option-label="label"
      option-value="value"
      placeholder="All actions"
      show-clear
      filter
      @update:model-value="onAction"
    />
  </div>

  <Message v-if="store.error" severity="error" :closable="false" class="mb">{{ store.error }}</Message>

  <DataTable :value="store.entries" :loading="store.loading" data-key="audit_id">
    <Column header="When">
      <template #body="{ data }">{{ formatDateTime(data.occurred_at) }}</template>
    </Column>
    <Column header="Who">
      <template #body="{ data }">{{ actorLabel(data) }}</template>
    </Column>
    <Column header="Action">
      <template #body="{ data }">{{ humanizeAction(data.action) }}</template>
    </Column>
    <Column header="Record">
      <template #body="{ data }">{{ targetLabel(data) }}</template>
    </Column>
    <Column header="Details">
      <template #body="{ data }">{{ formatDetail(data.detail) }}</template>
    </Column>
    <Column field="ip_address" header="From" />
    <template #empty>No entries match.</template>
  </DataTable>

  <div class="row sectop">
    <Button
      v-if="store.nextBeforeId != null"
      label="Load older entries"
      severity="secondary"
      :loading="store.loading"
      @click="store.more()"
    />
    <span class="muted">{{ store.entries.length }} shown</span>
  </div>
</template>