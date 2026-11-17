<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import Button from 'primevue/button'
import Card from 'primevue/card'

defineProps({
  title: { type: String, required: true },
  loading: { type: Boolean, default: false },
  empty: { type: Boolean, default: false },
  emptyText: { type: String, default: 'Nothing in this range.' },
  exportable: { type: Boolean, default: true },
  exporting: { type: Boolean, default: false },
})
defineEmits(['export'])
</script>

<template>
  <Card class="chart-card">
    <template #title>
      <div class="chart-head">
        <span class="grow">{{ title }}</span>
        <Button
          v-if="exportable"
          label="Export CSV"
          size="small"
          severity="secondary"
          text
          :loading="exporting"
          @click="$emit('export')"
        />
      </div>
    </template>
    <template #content>
      <p v-if="loading && empty" class="muted">Loading…</p>
      <p v-else-if="empty" class="muted">{{ emptyText }}</p>
      <slot v-else />
    </template>
  </Card>
</template>