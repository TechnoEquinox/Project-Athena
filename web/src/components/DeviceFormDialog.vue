<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import { addDevice, updateDevice } from '../clientsApi'
import { buildDevicePayload, deviceTypeOptions, emptyDeviceForm, fieldErrorFrom } from '../lib/forms'

const props = defineProps({
  clientId: { type: Number, required: true },
  device: { type: Object, default: null },
})
const visible = defineModel('visible', { type: Boolean, default: false })
const emit = defineEmits(['saved'])

const form = ref(emptyDeviceForm())
const errors = ref({})
const error = ref('')
const busy = ref(false)
const options = computed(() => deviceTypeOptions(props.device?.device_type))

watch(visible, (open) => {
  if (open) {
    form.value = emptyDeviceForm(props.device)
    errors.value = {}
    error.value = ''
  }
})

async function save() {
  error.value = ''
  errors.value = {}
  const payload = buildDevicePayload(form.value, props.device)
  if (props.device && Object.keys(payload).length === 0) {
    visible.value = false
    return
  }
  busy.value = true
  try {
    if (props.device) await updateDevice(props.clientId, props.device.device_id, payload)
    else await addDevice(props.clientId, payload)
    visible.value = false
    emit('saved')
  } catch (err) {
    const field = fieldErrorFrom(err)
    if (field) errors.value = { [field.field]: field.message }
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
    :header="device ? 'Edit device' : 'Add device'"
    :style="{ width: '26rem' }"
  >
    <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>
    <form class="form" @submit.prevent="save">
      <label id="dev-type-label">Type</label>
      <Select
        v-model="form.device_type"
        :options="options"
        placeholder="Choose a type"
        aria-labelledby="dev-type-label"
        fluid
      />
      <small v-if="errors.device_type" class="problem">{{ errors.device_type }}</small>

      <label for="dev-desc">Description (optional)</label>
      <InputText id="dev-desc" v-model="form.description" placeholder="iPhone 13, Samsung Galaxy Tab S7" autocomplete="off" fluid />
      <small v-if="errors.description" class="problem">{{ errors.description }}</small>

      <div class="row">
        <Button type="submit" :label="device ? 'Save changes' : 'Add device'" :loading="busy" :disabled="!form.device_type" />
        <Button type="button" label="Cancel" text severity="secondary" @click="visible = false" />
      </div>
    </form>
  </Dialog>
</template>