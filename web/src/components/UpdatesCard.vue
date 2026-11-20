<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Tag from 'primevue/tag'
import { packageRows, updatesSummary } from '../lib/server'

const props = defineProps({
  updates: { type: Object, default: null },
  rebootRequired: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})
defineEmits(['run'])

const summary = computed(() => updatesSummary(props.updates))
const packages = computed(() => packageRows(props.updates))
</script>

<template>
  <Card>
    <template #title>Ubuntu updates</template>
    <template #content>
      <p>
        <Tag :severity="summary.severity" :value="summary.severity === 'success' ? 'OK' : summary.severity === 'warn' ? 'Updates' : 'Unknown'" />
        {{ summary.text }}
      </p>
      <p v-if="rebootRequired" class="muted">A restart of the server is needed to finish earlier updates.</p>
      <ul v-if="packages.shown.length" class="plain pkg">
        <li v-for="p in packages.shown" :key="p.name">{{ p.name }} <span class="muted">{{ p.to }}</span></li>
        <li v-if="packages.hidden" class="muted">…and {{ packages.hidden }} more</li>
      </ul>
      <div class="sectop btnrow">
        <Button label="Check for updates" severity="secondary" icon="pi pi-refresh" :disabled="busy"
                @click="$emit('run', 'check-updates')" />
        <Button label="Install updates" icon="pi pi-download" :disabled="busy || !summary.count"
                @click="$emit('run', 'apply-updates')" />
      </div>
      <p class="muted">
        Installing can take several minutes. Athena keeps running, but may be slow. Some updates ask for a
        server restart afterwards. Back up first if you want to be extra careful.
      </p>
    </template>
  </Card>
</template>
