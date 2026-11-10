<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Message from 'primevue/message'
import AppointmentFormDialog from '../components/AppointmentFormDialog.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { deleteAppointment, getAppointment } from '../appointmentsApi'
import { formatDateTime } from '../lib/appointments'
import { useAuth } from '../stores/auth'

const props = defineProps({ id: { type: String, required: true } })
const auth = useAuth()
const router = useRouter()

const appointment = ref(null)
const notFound = ref(false)
const error = ref('')
const showEdit = ref(false)
const confirm = ref({ open: false, busy: false, error: '' })

async function load() {
  error.value = ''
  notFound.value = false
  try {
    appointment.value = await getAppointment(props.id)
  } catch (err) {
    appointment.value = null
    if (err.status === 404) notFound.value = true
    else error.value = err.message
  }
}
watch(() => props.id, load, { immediate: true })

async function remove() {
  confirm.value.busy = true
  confirm.value.error = ''
  try {
    await deleteAppointment(appointment.value.appointment_id)
    router.replace({ name: 'appointments', query: { deleted: '1' } })
  } catch (err) {
    confirm.value.error = err.message
  } finally {
    confirm.value.busy = false
  }
}
</script>

<template>
  <p><router-link :to="{ name: 'appointments' }">&larr; All appointments</router-link></p>

  <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
  <Message v-else-if="notFound" severity="warn" :closable="false">
    This appointment was not found. It may have been deleted.
  </Message>

  <template v-else-if="appointment">
    <div class="head">
      <h2>{{ formatDateTime(appointment.appointment_at) }}</h2>
      <div v-if="auth.canWrite" class="row">
        <Button label="Edit" severity="secondary" @click="showEdit = true" />
        <Button label="Delete" severity="danger" text @click="confirm = { open: true, busy: false, error: '' }" />
      </div>
    </div>

    <Card>
      <template #content>
        <dl class="facts">
          <dt>Client</dt>
          <dd>
            <router-link :to="{ name: 'client', params: { id: appointment.client.client_id } }">
              {{ appointment.client.first_name }} {{ appointment.client.last_name }}
            </router-link>
          </dd>
          <dt>Tech</dt>
          <dd>{{ appointment.tech.first_name }} {{ appointment.tech.last_name }}</dd>
          <dt>Location</dt>
          <dd>{{ appointment.location?.name ?? '—' }}</dd>
          <dt>Length</dt>
          <dd>{{ appointment.length_minutes }} minutes</dd>
          <dt>Devices</dt>
          <dd>
            <template v-if="appointment.devices.length">
              <div v-for="d in appointment.devices" :key="d.device_id">
                {{ d.device_type }}<span v-if="d.description">: {{ d.description }}</span>
                <span v-if="d.removed" class="muted"> (removed from the client)</span>
              </div>
            </template>
            <template v-else>—</template>
          </dd>
          <dt>Notes</dt>
          <dd class="notes">{{ appointment.notes || '—' }}</dd>
        </dl>
      </template>
    </Card>

    <AppointmentFormDialog v-model:visible="showEdit" :appointment="appointment" @saved="(a) => (appointment = a)" />
    <ConfirmDialog
      v-model:visible="confirm.open"
      title="Delete this appointment?"
      message="It will be hidden from lists and reports. An admin can restore it for a limited time."
      confirm-label="Delete appointment"
      :busy="confirm.busy"
      :error="confirm.error"
      @confirm="remove"
    />
  </template>
</template>