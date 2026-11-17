<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, onMounted, ref } from 'vue'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import SelectButton from 'primevue/selectbutton'
import {
  MAP_SIZE, NEUTRAL, buildMap, stepLabel, summarize, tooltipText, zipRows,
} from '../lib/zipmap'

const props = defineProps({ report: { type: Object, required: true } })

const features = ref(null)
const loadError = ref('')
const mode = ref('focus')
const tip = ref(null)
const box = ref(null)

const modes = [
  { label: 'Zoom to clients', value: 'focus' },
  { label: 'All of Connecticut', value: 'state' },
]

// The boundary data loads only when the map is shown
onMounted(async () => {
  try {
    features.value = (await import('../data/ct-zcta.json')).default.features
  } catch {
    loadError.value = 'The map data could not be loaded.'
  }
})

const map = computed(() => (features.value ? buildMap(features.value, props.report, { mode: mode.value }) : null))
const facts = computed(() => summarize(props.report, map.value?.unmappedClients ?? 0))
const rows = computed(() => zipRows(props.report))

function onMove(event, p) {
  const rect = box.value.getBoundingClientRect()
  tip.value = { text: tooltipText(p.zip, p.count), x: event.clientX - rect.left, y: event.clientY - rect.top }
}

function onFocus(p) {
  const scale = box.value.getBoundingClientRect().width / MAP_SIZE.width
  tip.value = { text: tooltipText(p.zip, p.count), x: p.center[0] * scale, y: p.center[1] * scale }
}
</script>

<template>
  <div class="map-layout">
    <div>
      <SelectButton
        v-model="mode"
        :options="modes"
        option-label="label"
        option-value="value"
        :allow-empty="false"
        class="mb"
        aria-label="Map zoom"
      />
      <p v-if="loadError" class="problem">{{ loadError }}</p>
      <p v-else-if="!map" class="muted">Loading the map…</p>

      <div v-else ref="box" class="map-wrap" @mouseleave="tip = null">
        <svg
          :viewBox="`0 0 ${MAP_SIZE.width} ${MAP_SIZE.height}`"
          role="group"
          aria-label="Map of Connecticut ZIP codes, shaded by the number of clients"
        >
          <path
            v-for="p in map.paths"
            :key="p.zip"
            :d="p.d"
            :fill="p.color"
            class="zip"
            :class="{ live: p.count > 0 }"
            :tabindex="p.count > 0 ? 0 : -1"
            :role="p.count > 0 ? 'img' : undefined"
            :aria-label="p.count > 0 ? tooltipText(p.zip, p.count) : undefined"
            @mousemove="onMove($event, p)"
            @mouseleave="tip = null"
            @focus="onFocus(p)"
            @blur="tip = null"
          />
        </svg>
        <div v-if="tip" class="map-tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">{{ tip.text }}</div>
      </div>

      <div v-if="map" class="legend sectop">
        <span><i class="swatch" :style="{ background: NEUTRAL }" />No clients</span>
        <span v-for="s in map.steps" :key="s.from"><i class="swatch" :style="{ background: s.color }" />{{ stepLabel(s) }}</span>
      </div>
      <p class="muted">
        Areas are Census ZIP Code Tabulation Areas, which approximate ZIP codes. Counts are unique clients
        with at least one appointment in the selected range.
      </p>
    </div>

    <div>
      <dl class="facts">
        <dt>Clients</dt><dd>{{ facts.total }}</dd>
        <dt>In Connecticut</dt><dd>{{ facts.connecticut }} across {{ facts.zipCount }} ZIP code(s)</dd>
        <dt>Outside Connecticut</dt><dd>{{ facts.other }}</dd>
        <dt>No ZIP recorded</dt><dd>{{ facts.noZip }}</dd>
      </dl>
      <p v-if="map && facts.unmapped" class="muted">
        {{ facts.unmapped }} client(s) live in ZIP code(s) with no map area:
        {{ map.unmapped.map((z) => z.zipcode).join(', ') }}. They are in the table and the CSV.
      </p>
      <DataTable :value="rows" data-key="key" scrollable scroll-height="20rem" class="sectop">
        <Column field="label" header="ZIP code" />
        <Column field="clients" header="Clients" />
        <template #empty>No clients in this range.</template>
      </DataTable>
    </div>
  </div>
</template>