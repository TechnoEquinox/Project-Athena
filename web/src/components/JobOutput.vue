<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Message from 'primevue/message'
import ProgressBar from 'primevue/progressbar'
import Tag from 'primevue/tag'
import { actionLabel, isFinished, jobOutcome, jobState } from '../lib/server'

const props = defineProps({
  job: { type: Object, required: true },
  log: { type: String, default: '' },
  active: { type: Boolean, default: false },
  lostContact: { type: Boolean, default: false },
})
defineEmits(['dismiss'])

const state = computed(() => jobState(props.job.state))
const finished = computed(() => isFinished(props.job.state))
const outcome = computed(() => jobOutcome(props.job))
</script>

<template>
  <Card class="mb">
    <template #title>
      <div class="chart-head">
        <span class="grow">{{ actionLabel(job.action) }}</span>
        <Tag :severity="state.severity" :value="state.label" />
      </div>
    </template>
    <template #content>
      <ProgressBar v-if="active && !finished" mode="indeterminate" style="height: 6px" class="mb" />
      <Message v-if="active && lostContact" severity="info" :closable="false" class="mb">
        Lost contact with the server for a moment. This is normal while Athena restarts. Still trying…
      </Message>
      <Message v-if="finished && outcome" :severity="job.state === 'succeeded' ? 'success' : 'error'"
               :closable="false" class="mb">{{ outcome }}</Message>
      <pre v-if="log" class="joblog">{{ log }}</pre>
      <p v-else-if="!finished" class="muted">Waiting for the server to start this job…</p>
      <div v-if="finished" class="sectop">
        <Button label="Close" severity="secondary" size="small" @click="$emit('dismiss')" />
      </div>
    </template>
  </Card>
</template>
