<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { ref, watch } from 'vue'
import DatePicker from 'primevue/datepicker'
import Message from 'primevue/message'
import Select from 'primevue/select'
import { listSlots } from '../schedulingApi'
import { formatSlot, schedulingErrorMessage, toLocalISODate } from '../lib/scheduling'

const props = defineProps({
  techId: { type: Number, default: null },
  excludeBookingId: { type: Number, default: null },
  initialDate: { type: Date, default: null },
})
const startsAt = defineModel({ default: null })   // ISO string of the chosen slot

const day = ref(props.initialDate)
const slots = ref([])
const closed = ref('')
const error = ref('')
const loading = ref(false)

let sequence = 0
async function load() {
  startsAt.value = null
  slots.value = []
  closed.value = ''
  error.value = ''
  if (!props.techId || !day.value) return
  const mine = ++sequence
  loading.value = true
  try {
    const found = await listSlots({
      techId: props.techId, date: toLocalISODate(day.value), excludeBookingId: props.excludeBookingId,
    })
    if (mine === sequence) {
      slots.value = found.slots.map((iso) => ({ iso, label: formatSlot(iso) }))
      closed.value = found.blocked?.description ?? ''
    }
  } catch (err) {
    if (mine === sequence) error.value = schedulingErrorMessage(err)
  } finally {
    if (mine === sequence) loading.value = false
  }
}

watch(() => [props.techId, day.value], load, { immediate: true })
</script>

<template>
  <div class="field">
    <label for="slot-date">Date</label>
    <DatePicker v-model="day" input-id="slot-date" :min-date="new Date()" date-format="mm/dd/yy" fluid />
  </div>
  <div class="field">
    <label for="slot-time">Time</label>
    <Select
      v-model="startsAt"
      input-id="slot-time"
      :options="slots"
      option-label="label"
      option-value="iso"
      :loading="loading"
      :disabled="!techId || !day || !slots.length"
      :placeholder="!techId || !day ? 'Pick a navigator and a date' : slots.length ? 'Pick a time' : 'No open times that day'"
      fluid
    />
  </div>
  <Message v-if="closed" severity="warn" :closable="false" class="mb">ALERT: Availability shows that you are unavailable on {{ closed }}</Message>
  <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
</template>

<style scoped>
.field { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 1rem; }
</style>