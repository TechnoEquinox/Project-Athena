<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import ClientPicker from './ClientPicker.vue'
import { createAppointment, updateAppointment } from '../appointmentsApi'
import { getClient } from '../clientsApi'
import {
  buildAppointmentPayload, deviceOptions, emptyAppointmentForm, locationOptions, techOptions,
} from '../lib/appointments'
import { fieldErrorFrom } from '../lib/forms'
import { listLocations } from '../locationsApi'
import { useAuth } from '../stores/auth'
import { listTechs } from '../techsApi'

const props = defineProps({
  appointment: { type: Object, default: null },   // set when editing
  client: { type: Object, default: null },        // { client_id, label }: fixes the client
})
const visible = defineModel('visible', { type: Boolean, default: false })
const emit = defineEmits(['saved'])
const auth = useAuth()

const form = ref(emptyAppointmentForm())
const errors = ref({})
const error = ref('')
const busy = ref(false)
const maxDate = ref(new Date())

const locations = ref([])
const techs = ref([])
const clientDevices = ref([])

const clientFixed = computed(() => !!props.appointment || !!props.client)
const locationChoices = computed(() => locationOptions(locations.value, props.appointment?.location))
const techChoices = computed(() => techOptions(techs.value, props.appointment?.tech))
const deviceChoices = computed(() => deviceOptions(clientDevices.value, props.appointment?.devices))

async function loadDevices(clientId) {
  clientDevices.value = []
  if (!clientId) return
  try {
    clientDevices.value = (await getClient(clientId)).devices
  } catch {
    clientDevices.value = []
  }
}

watch(visible, async (open) => {
  if (!open) return
  form.value = emptyAppointmentForm(props.appointment, {
    client: props.client,
    techId: auth.user?.tech_id ?? null,
  })
  errors.value = {}
  error.value = ''
  maxDate.value = new Date()
  const [locs, tchs] = await Promise.all([
    listLocations().catch(() => []),
    auth.isAdmin ? listTechs().catch(() => []) : Promise.resolve([]),
  ])
  locations.value = locs
  techs.value = tchs
  await loadDevices(form.value.client?.client_id)
})

function picked(client) {
  form.value.device_ids = []
  loadDevices(client.client_id)
}

const canSubmit = computed(() => {
  const f = form.value
  return (
    !!f.client?.client_id &&
    f.when instanceof Date && !Number.isNaN(f.when.getTime()) &&
    !!f.location_id &&
    Number.isInteger(f.length_minutes) && f.length_minutes >= 1 &&
    (!auth.isAdmin || !!f.tech_id)
  )
})

async function save() {
  error.value = ''
  errors.value = {}
  const payload = buildAppointmentPayload(form.value, props.appointment, { sendTech: auth.isAdmin })
  if (props.appointment && Object.keys(payload).length === 0) {
    visible.value = false
    return
  }
  busy.value = true
  try {
    const saved = props.appointment
      ? await updateAppointment(props.appointment.appointment_id, payload)
      : await createAppointment(payload)
    visible.value = false
    emit('saved', saved)
  } catch (err) {
    const field = fieldErrorFrom(err)
    if (field) errors.value = { [field.field]: field.message }
    else if (err.code === 'forbidden_field') error.value = 'You cannot change the tech on an appointment.'
    else if (err.status === 404) error.value = 'That appointment or client no longer exists.'
    else error.value = err.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    :header="appointment ? 'Edit appointment' : 'Log appointment'"
    :style="{ width: '34rem' }"
  >
    <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>
    <form class="form" @submit.prevent="save">
      <label :for="clientFixed ? undefined : 'ap-client'">Client</label>
      <strong v-if="clientFixed">{{ form.client?.label }}</strong>
      <ClientPicker v-else v-model="form.client" @picked="picked" />
      <small v-if="errors.client_id" class="problem">{{ errors.client_id }}</small>

      <label for="ap-when">Date and time</label>
      <DatePicker
        v-model="form.when"
        input-id="ap-when"
        show-time
        hour-format="12"
        show-icon
        :max-date="maxDate"
        fluid
      />
      <small v-if="errors.appointment_at" class="problem">{{ errors.appointment_at }}</small>

      <label id="ap-loc-label">Location</label>
      <Select
        v-model="form.location_id"
        :options="locationChoices"
        option-label="name"
        option-value="location_id"
        placeholder="Choose a location"
        aria-labelledby="ap-loc-label"
        fluid
      />
      <small v-if="!locationChoices.length" class="muted">
        No locations are set up yet. An admin can add them under Locations.
      </small>
      <small v-if="errors.location_id" class="problem">{{ errors.location_id }}</small>

      <label for="ap-len">Length (minutes)</label>
      <InputNumber
        v-model="form.length_minutes"
        input-id="ap-len"
        :min="1"
        :max="600"
        :use-grouping="false"
        suffix=" min"
        fluid
      />
      <small v-if="errors.length_minutes" class="problem">{{ errors.length_minutes }}</small>

      <label id="ap-dev-label">Devices (optional)</label>
      <MultiSelect
        v-model="form.device_ids"
        :options="deviceChoices"
        option-label="label"
        option-value="device_id"
        display="chip"
        :show-toggle-all="false"
        :placeholder="form.client?.client_id ? 'Choose devices' : 'Pick a client first'"
        :disabled="!form.client?.client_id"
        aria-labelledby="ap-dev-label"
        fluid
      />
      <small v-if="form.client?.client_id && !deviceChoices.length" class="muted">
        This client has no devices yet. Add them on the client's page.
      </small>
      <small v-if="errors.device_ids" class="problem">{{ errors.device_ids }}</small>

      <template v-if="auth.isAdmin">
        <label id="ap-tech-label">Tech</label>
        <Select
          v-model="form.tech_id"
          :options="techChoices"
          option-label="label"
          option-value="tech_id"
          placeholder="Choose a tech"
          aria-labelledby="ap-tech-label"
          fluid
        />
        <small v-if="errors.tech_id" class="problem">{{ errors.tech_id }}</small>
      </template>
      <small v-else-if="!appointment" class="muted">This will be recorded under your name.</small>

      <label for="ap-notes">Notes (optional)</label>
      <Textarea v-model="form.notes" input-id="ap-notes" rows="3" auto-resize maxlength="5000" fluid />
      <small v-if="errors.notes" class="problem">{{ errors.notes }}</small>

      <div class="row">
        <Button
          type="submit"
          :label="appointment ? 'Save changes' : 'Log appointment'"
          :loading="busy"
          :disabled="!canSubmit"
        />
        <Button type="button" label="Cancel" text severity="secondary" @click="visible = false" />
      </div>
    </form>
  </Dialog>
</template>