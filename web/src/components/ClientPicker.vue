<script setup>
import { ref } from 'vue'
import AutoComplete from 'primevue/autocomplete'
import { listClients } from '../clientsApi'
import { clientLabel } from '../lib/appointments'
import { formatPhone } from '../lib/forms'

const model = defineModel({ default: null })   // { client_id, label } once a client is picked
const emit = defineEmits(['picked'])
const suggestions = ref([])

async function search(event) {
  const q = event.query.trim()
  if (!q) {
    suggestions.value = []
    return
  }
  try {
    const data = await listClients({ q, limit: 10, offset: 0 })
    suggestions.value = data.clients.map((c) => ({
      client_id: c.client_id,
      label: clientLabel(c) + (c.phone ? ` · ${formatPhone(c.phone)}` : ''),
    }))
  } catch {
    suggestions.value = []
  }
}
</script>

<template>
  <AutoComplete
    v-model="model"
    :suggestions="suggestions"
    option-label="label"
    input-id="ap-client"
    placeholder="Search by name, phone or email"
    force-selection
    :delay="300"
    fluid
    @complete="search"
    @item-select="(event) => emit('picked', event.value)"
  />
</template>