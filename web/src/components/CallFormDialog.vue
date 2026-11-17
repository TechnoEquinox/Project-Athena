<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import ClientPicker from './ClientPicker.vue'
import { createCall, listStatuses, updateCall } from '../callsApi'
import { techOptions } from '../lib/appointments'
import { buildCallPayload, emptyCallForm, hasCaller } from '../lib/calls'
import { fieldErrorFrom } from '../lib/forms'
import { useAuth } from '../stores/auth'
import { listTechs } from '../techsApi'

const props = defineProps({
  call: { type: Object, default: null },     // set when editing
  client: { type: Object, default: null },   // { client_id, label }: links to existing client
})
const visible = defineModel('visible', { type: Boolean, default: false })
const emit = defineEmits(['saved'])
const auth = useAuth()

const form = ref(emptyCallForm())
const defaultWhen = ref(null)
const errors = ref({})
const error = ref('')
const busy = ref(false)
const maxDate = ref(new Date())
const statuses = ref([])
const techs = ref([])
const techChoices = computed(() => techOptions(techs.value, props.call?.tech))
const clientFixed = computed(() => !!props.client)

watch(visible, async (open) => {
  if (!open) return
  form.value = emptyCallForm(props.call, {
    techId: auth.user?.tech_id ?? null,
    client: props.client,
  })
  defaultWhen.value = props.call ? null : new Date(form.value.when.getTime())
  errors.value = {}
  error.value = ''
  maxDate.value = new Date()
  const [s, t] = await Promise.all([
    listStatuses().catch(() => []),
    auth.isAdmin ? listTechs().catch(() => []) : Promise.resolve([]),
  ])
  statuses.value = s
  techs.value = t
})

const canSubmit = computed(() => {
  const f = form.value
  return (
    !!f.status &&
    f.when instanceof Date && !Number.isNaN(f.when.getTime()) &&
    hasCaller(f) &&
    (!auth.isAdmin || !!f.tech_id)
  )
})

async function save() {
  error.value = ''
  errors.value = {}
  const payload = buildCallPayload(form.value, props.call, {
    sendTech: auth.isAdmin,
    defaultWhen: defaultWhen.value,
  })
  if (props.call && Object.keys(payload).length === 0) {
    visible.value = false
    return
  }
  busy.value = true
  try {
    const saved = props.call
      ? await updateCall(props.call.call_id, payload)
      : await createCall(payload)
    visible.value = false
    emit('saved', saved)
  } catch (err) {
    const field = fieldErrorFrom(err)
    if (field) errors.value = { [field.field]: field.message }
    else if (err.code === 'forbidden_field') error.value = 'You cannot change the tech on a call.'
    else if (err.code === 'not_found') error.value = 'That call or client no longer exists.'
    else if (err.status === 404) error.value = 'The server does not have this feature yet. Ask an admin to update it.'
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
    :header="call ? 'Edit call' : 'Log call'"
    :style="{ width: '34rem' }"
  >
    <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>
    <form class="form" @submit.prevent="save">
      <label id="call-status-label">Status</label>
      <Select
        v-model="form.status"
        :options="statuses"
        option-label="label"
        option-value="value"
        placeholder="Choose a status"
        aria-labelledby="call-status-label"
        fluid
      />
      <small v-if="errors.status" class="problem">{{ errors.status }}</small>

      <label for="call-when">Call received</label>
      <DatePicker
        v-model="form.when"
        input-id="call-when"
        show-time
        hour-format="12"
        show-icon
        :max-date="maxDate"
        fluid
      />
      <small class="muted">Defaults to now. Change it for a voicemail left earlier, such as over the weekend.</small>
      <small v-if="errors.called_at" class="problem">{{ errors.called_at }}</small>

      <label for="call-first">First name (optional)</label>
      <InputText id="call-first" v-model="form.first_name" autocomplete="off" fluid />
      <small v-if="errors.client_first_name" class="problem">{{ errors.client_first_name }}</small>

      <label for="call-last">Last name (optional)</label>
      <InputText id="call-last" v-model="form.last_name" autocomplete="off" fluid />
      <small v-if="errors.client_last_name" class="problem">{{ errors.client_last_name }}</small>

      <label for="call-phone">Phone (optional)</label>
      <InputText id="call-phone" v-model="form.phone" inputmode="tel" autocomplete="off" fluid />
      <small v-if="errors.phone" class="problem">{{ errors.phone }}</small>

      <label :for="clientFixed ? undefined : 'ap-client'">
        {{ clientFixed ? 'Client' : 'Link to an existing client (optional)' }}
      </label>
      <template v-if="clientFixed">
        <strong>{{ client.label }}</strong>
        <small class="muted">Linked to this client. The name and phone above stay as typed.</small>
      </template>
      <template v-else>
        <ClientPicker v-model="form.client" />
        <div v-if="form.client" class="row">
          <small class="muted">Linked. The name and phone above stay as typed.</small>
          <Button type="button" label="Unlink" size="small" text severity="secondary" @click="form.client = null" />
        </div>
      </template>
      <small v-if="errors.client_id" class="problem">{{ errors.client_id }}</small>

      <template v-if="auth.isAdmin">
        <label id="call-tech-label">Tech</label>
        <Select
          v-model="form.tech_id"
          :options="techChoices"
          option-label="label"
          option-value="tech_id"
          placeholder="Choose a tech"
          aria-labelledby="call-tech-label"
          fluid
        />
        <small v-if="errors.tech_id" class="problem">{{ errors.tech_id }}</small>
      </template>
      <small v-else-if="!call" class="muted">This will be recorded under your name.</small>

      <label for="call-notes">Notes (optional)</label>
      <Textarea v-model="form.notes" input-id="call-notes" rows="3" auto-resize maxlength="5000" fluid />
      <small v-if="errors.notes" class="problem">{{ errors.notes }}</small>

      <div class="row">
        <Button
          type="submit"
          :label="call ? 'Save changes' : 'Log call'"
          :loading="busy"
          :disabled="!canSubmit"
        />
        <Button type="button" label="Cancel" text severity="secondary" @click="visible = false" />
      </div>
    </form>
  </Dialog>
</template>