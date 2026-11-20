<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Tag from 'primevue/tag'
import { backupRows, backupSummary, formatBytes } from '../lib/server'

const props = defineProps({
  backups: { type: Object, default: null },
  busy: { type: Boolean, default: false },
})
defineEmits(['run'])

const summary = computed(() => backupSummary(props.backups))
const rows = computed(() => backupRows(props.backups))
const total = computed(() => props.backups?.total_files ?? 0)
</script>

<template>
  <Card>
    <template #title>Backups</template>
    <template #content>
      <ul class="plain">
        <li><Tag :severity="summary.last.severity" :value="summary.last.severity === 'success' ? 'OK' : 'Check'" />
          {{ summary.last.text }}</li>
        <li><Tag :severity="summary.usb.severity" :value="summary.usb.severity === 'success' ? 'OK' : 'Check'" />
          {{ summary.usb.text }}</li>
      </ul>
      <div class="sectop">
        <Button label="Back up now" icon="pi pi-download" :disabled="busy" @click="$emit('run', 'backup')" />
        <span class="muted"> Takes a minute. A copy also goes to a plugged-in USB drive.</span>
      </div>
      <h4 class="sectop">Recent backups on this server</h4>
      <p v-if="!rows.length" class="muted">No backups yet.</p>
      <template v-else>
        <DataTable :value="rows" data-key="name" size="small">
          <Column header="Made">
            <template #body="{ data }">{{ data.when ? data.when.toLocaleString() : data.name }}</template>
          </Column>
          <Column header="Size">
            <template #body="{ data }">{{ formatBytes(data.bytes) }}</template>
          </Column>
        </DataTable>
        <p v-if="total > rows.length" class="muted">Showing {{ rows.length }} of {{ total }} backups.</p>
      </template>
    </template>
  </Card>
</template>
