<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import ConfirmDialog from './ConfirmDialog.vue'
import SlotPicker from './SlotPicker.vue'
import { deleteBooking, getBooking, updateBooking } from '../schedulingApi'
import {
  contactRows, formatBookingTime, navigatorName, schedulingErrorMessage, STATUS_LABELS,
} from '../lib/scheduling'
import { useAuth } from '../stores/auth'

const props = defineProps({ bookingId: { type: Number, default: null } })
const emit = defineEmits(['changed'])
const visible = defineModel('visible', { type: Boolean, default: false })

const auth = useAuth()
const booking = ref(null)
const error = ref('')
const busy = ref(false)
const moving = ref(false)
const newStart = ref(null)
const confirmDelete = ref(false)

const canEdit = computed(
  () => auth.canWrite && booking.value &&
    (auth.user.role === 'admin' || booking.value.tech.tech_id === auth.user.tech_id),
)
const isScheduled = computed(() => booking.value?.status === 'scheduled')
const rows = computed(() => (booking.value ? contactRows(booking.value.client) : []))

watch(() => [visible.value, props.bookingId], async ([open, id]) => {
  booking.value = null
  moving.value = false
  newStart.value = null
  error.value = ''
  if (!open || !id) return
  try {
    booking.value = await getBooking(id)
  } catch (err) {
    error.value = schedulingErrorMessage(err)
  }
})

async function run(action, { close = false } = {}) {
  busy.value = true
  error.value = ''
  try {
    const result = await action()
    if (result) booking.value = result
    moving.value = false
    emit('changed')
    if (close) visible.value = false
  } catch (err) {
    error.value = schedulingErrorMessage(err)
    confirmDelete.value = false
  } finally {
    busy.value = false
  }
}

const setStatus = (status) => run(() => updateBooking(booking.value.booking_id, { status }))
const reschedule = () => run(() => updateBooking(booking.value.booking_id, { starts_at: newStart.value }))
const remove = () => run(async () => {
  await deleteBooking(booking.value.booking_id)
  confirmDelete.value = false
}, { close: true })
</script>

<template>
  <Dialog v-model:visible="visible" modal header="Appointment" :style="{ width: '36rem', maxWidth: '95vw' }">
    <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>
    <template v-if="booking">
      <h3 class="name">
        <router-link :to="{ name: 'client', params: { id: booking.client.client_id } }">
          {{ booking.client.first_name }} {{ booking.client.last_name }}
        </router-link>
        <Tag :value="STATUS_LABELS[booking.status]" :severity="isScheduled ? 'info' : 'secondary'" />
      </h3>
      <p>{{ formatBookingTime(booking.starts_at) }} with {{ navigatorName(booking.tech) }}</p>
      <dl class="contact">
        <template v-for="row in rows" :key="row.label">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.value }}</dd>
        </template>
      </dl>
      <p v-if="booking.notes" class="notes">{{ booking.notes }}</p>

      <div v-if="moving" class="move">
        <SlotPicker
          v-model="newStart" :tech-id="booking.tech.tech_id"
          :exclude-booking-id="booking.booking_id" :initial-date="new Date(booking.starts_at)"
        />
        <Button label="Move" :disabled="!newStart" :loading="busy" @click="reschedule" />
        <Button label="Never mind" text severity="secondary" @click="moving = false" />
      </div>
    </template>

    <template #footer>
      <div class="actions">
      <template v-if="canEdit && booking && !moving">
        <Button v-if="isScheduled" label="Reschedule" text @click="moving = true" />
        <Button v-if="isScheduled" label="Cancel appointment" text severity="secondary" :loading="busy" @click="setStatus('cancelled')" />
        <Button v-if="isScheduled" label="No-show" text severity="secondary" :loading="busy" @click="setStatus('no_show')" />
        <Button v-if="isScheduled" label="Completed" text :loading="busy" @click="setStatus('completed')" />
        <Button v-if="!isScheduled" label="Reopen" text :loading="busy" @click="setStatus('scheduled')" />
        <Button label="Delete" text severity="danger" @click="confirmDelete = true" />
      </template>
      <Button label="Close" severity="secondary" @click="visible = false" />
      </div>
    </template>
  </Dialog>

  <ConfirmDialog
    v-model:visible="confirmDelete" title="Delete this appointment?"
    message="It disappears from the calendar and the time opens up again." confirm-label="Delete"
    :busy="busy" @confirm="remove"
  />
</template>

<style scoped>
.name { display: flex; align-items: center; gap: 0.75rem; margin: 0 0 0.25rem; }
.contact { display: grid; grid-template-columns: max-content 1fr; gap: 0.25rem 1rem; margin: 0 0 1rem; }
.contact dt { color: #6b7280; }
.contact dd { margin: 0; }
.notes { white-space: pre-wrap; }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.25rem; width: 100%; }
.actions :deep(.p-button) { white-space: nowrap; flex: 0 0 auto; }
.move { display: flex; flex-direction: column; gap: 0.5rem; }
</style>