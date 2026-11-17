<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref, watch } from 'vue'
import DatePicker from 'primevue/datepicker'
import Message from 'primevue/message'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import { formatYmd, parseYmd } from '../lib/admin'
import { INTERVAL_OPTIONS, MODE_OPTIONS, presetOptions, rangeLabel } from '../lib/dashboard'
import { useDashboard } from '../stores/dashboard'

const store = useDashboard()

const presets = computed(() => (store.today ? presetOptions(store.today, store.fiscalStartMonth) : []))
const pickedPreset = computed(() => (store.preset === 'custom' ? null : store.preset))

// The picker keeps its own value while a range is half-picked, and follows the store otherwise
const picker = ref(null)
watch(
  () => [store.from, store.to],
  ([from, to]) => { picker.value = from && to ? [parseYmd(from), parseYmd(to)] : null },
  { immediate: true },
)

function onRange(value) {
  picker.value = value
  if (Array.isArray(value) && value[0] && value[1]) {
    store.setCustom(formatYmd(value[0]), formatYmd(value[1]))
  }
}
</script>

<template>
  <div class="dash-controls">
    <div class="ctl">
      <label id="dash-preset-label">Date range</label>
      <Select
        :model-value="pickedPreset"
        :options="presets"
        option-label="label"
        option-value="key"
        placeholder="Custom range"
        aria-labelledby="dash-preset-label"
        @update:model-value="store.setPreset"
      />
    </div>
    <div class="ctl">
      <label for="dash-custom">Custom dates</label>
      <DatePicker
        :model-value="picker"
        input-id="dash-custom"
        selection-mode="range"
        show-icon
        :manual-input="false"
        placeholder="Pick a start and end"
        @update:model-value="onRange"
      />
    </div>
    <div class="ctl">
      <label id="dash-interval-label">Group by</label>
      <SelectButton
        :model-value="store.interval"
        :options="INTERVAL_OPTIONS"
        option-label="label"
        option-value="value"
        :allow-empty="false"
        aria-labelledby="dash-interval-label"
        @update:model-value="store.setInterval"
      />
    </div>
    <div class="ctl">
      <label id="dash-mode-label">Breakdown</label>
      <SelectButton
        :model-value="store.mode"
        :options="MODE_OPTIONS"
        option-label="label"
        option-value="value"
        :allow-empty="false"
        aria-labelledby="dash-mode-label"
        @update:model-value="store.setMode"
      />
    </div>
  </div>
  <p v-if="store.from" class="muted">
    Showing {{ rangeLabel(store.from, store.to) }}<span v-if="store.timezone">. Periods follow {{ store.timezone }} time.</span>
  </p>
  <Message v-if="store.rangeError" severity="warn" :closable="false" class="mb">{{ store.rangeError }}</Message>
</template>