<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import ClientPicker from './ClientPicker.vue'
import SlotPicker from './SlotPicker.vue'
import { getClient } from '../clientsApi'
import { createBooking } from '../schedulingApi'
import { contactRows, navigatorName, schedulingErrorMessage } from '../lib/scheduling'
import { useAuth } from '../stores/auth'

const props = defineProps({
  navigators: { type: Array, default: () => [] },
  initialDate: { type: Date, default: null },
  initialTechId: { type: Number, default: null },
})
const emit = defineEmits(['saved'])
const visible = defineModel('visible', { type: Boolean, default: false })

const auth = useAuth()
const isNavigator = computed(() => auth.user?.role === 'navigator')

const picked = ref(null)
const contact = ref(null)
const techId = ref(null)
const startsAt = ref(null)
const notes = ref('')
const busy = ref(false)
const error = ref('')

const options = computed(() => props.navigators.map((n) => ({ tech_id: n.tech_id, label: navigatorName(n) })))

watch(visible, (open) => {
  if (!open) return
  picked.value = null
  contact.value = null
  startsAt.value = null
  notes.value = ''
  error.value = ''
  techId.value = isNavigator.value ? auth.user.tech_id : props.initialTechId
})

// Pull the client's email, phone and language as soon as they are picked.
async function onPicked(item) {
  contact.value = null
  try {
    contact.value = contactRows(await getClient(item.client_id))
  } catch (err) {
    error.value = schedulingErrorMessage(err)
  }
}

const ready = computed(() => picked.value?.client_id && techId.value && startsAt.value)

async function save() {
  busy.value = true
  error.value = ''
  try {
    const body = { client_id: picked.value.client_id, starts_at: startsAt.value }
    if (notes.value.trim()) body.notes = notes.value.trim()
    if (!isNavigator.value) body.tech_id = techId.value
    await createBooking(body)
    visible.value = false
    emit('saved')
  } catch (err) {
    error.value = schedulingErrorMessage(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" modal header="Book an appointment" :style="{ width: '30rem' }">
    <div class="field">
      <label for="ap-client">Client</label>
      <ClientPicker v-model="picked" @picked="onPicked" />
      <small class="muted">Only existing clients can be booked.</small>
    </div>
    <dl v-if="contact" class="contact">
      <template v-for="row in contact" :key="row.label">
        <dt>{{ row.label }}</dt>
        <dd>{{ row.value }}</dd>
      </template>
    </dl>

    <div v-if="!isNavigator" class="field">
      <label for="book-tech">Digital Navigator</label>
      <Select
        v-model="techId" input-id="book-tech" :options="options" option-label="label"
        option-value="tech_id" placeholder="Pick a navigator" fluid
      />
    </div>
    <SlotPicker v-model="startsAt" :tech-id="techId" :initial-date="initialDate" />

    <div class="field">
      <label for="book-notes">Notes (optional)</label>
      <Textarea id="book-notes" v-model="notes" rows="3" maxlength="5000" fluid />
    </div>
    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

    <template #footer>
      <Button label="Cancel" text severity="secondary" :disabled="busy" @click="visible = false" />
      <Button label="Book" :disabled="!ready" :loading="busy" @click="save" />
    </template>
  </Dialog>
</template>

<style scoped>
.field { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 1rem; }
.contact { display: grid; grid-template-columns: max-content 1fr; gap: 0.25rem 1rem; margin: 0 0 1rem; }
.contact dt { color: #6b7280; }
.contact dd { margin: 0; }
</style>