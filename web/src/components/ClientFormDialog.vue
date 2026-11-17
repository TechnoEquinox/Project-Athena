<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import { createClient, updateClient } from '../clientsApi'
import {
  MAX_LANGUAGES, buildClientPayload, emptyClientForm, fieldErrorFrom, formatPhone, languageOptions,
} from '../lib/forms'

const props = defineProps({ client: { type: Object, default: null } })
const visible = defineModel('visible', { type: Boolean, default: false })
const emit = defineEmits(['saved'])

const form = ref(emptyClientForm())
const errors = ref({})
const error = ref('')
const busy = ref(false)
const duplicates = ref([])

const languages = computed(() => languageOptions(props.client?.languages))

watch(visible, (open) => {
  if (open) {
    form.value = emptyClientForm(props.client)
    errors.value = {}
    error.value = ''
    duplicates.value = []
  }
})

const canSave = () => form.value.first_name.trim() && form.value.last_name.trim()

async function save(force = false) {
  error.value = ''
  errors.value = {}
  const payload = buildClientPayload(form.value, props.client)
  if (props.client && Object.keys(payload).length === 0) {
    visible.value = false
    return
  }
  busy.value = true
  try {
    const saved = props.client
      ? await updateClient(props.client.client_id, payload)
      : await createClient(payload, { force })
    visible.value = false
    emit('saved', saved)
  } catch (err) {
    const field = fieldErrorFrom(err)
    if (err.code === 'possible_duplicate') {
      duplicates.value = err.body.matches ?? []
    } else if (field) {
      errors.value = { [field.field]: field.message }
    } else {
      error.value = err.message
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    :header="client ? 'Edit client' : 'Add client'"
    :style="{ width: '30rem' }"
  >
    <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

    <div v-if="duplicates.length">
      <Message severity="warn" :closable="false" class="mb">
        A client with this name and phone number may already exist:
      </Message>
      <ul class="matches">
        <li v-for="m in duplicates" :key="m.client_id">
          <router-link
            :to="{ name: 'client', params: { id: m.client_id } }"
            @click="visible = false"
          >{{ m.last_name }}, {{ m.first_name }}</router-link>
          <span class="muted"> {{ formatPhone(m.phone) }} {{ m.zipcode }}</span>
        </li>
      </ul>
      <div class="row">
        <Button label="Create anyway" severity="warn" :loading="busy" @click="save(true)" />
        <Button label="Go back and edit" text severity="secondary" @click="duplicates = []" />
      </div>
    </div>

    <form v-else class="form" @submit.prevent="save(false)">
      <label for="cf-first">First name</label>
      <InputText id="cf-first" v-model="form.first_name" autocomplete="off" fluid />
      <small v-if="errors.first_name" class="problem">{{ errors.first_name }}</small>

      <label for="cf-last">Last name</label>
      <InputText id="cf-last" v-model="form.last_name" autocomplete="off" fluid />
      <small v-if="errors.last_name" class="problem">{{ errors.last_name }}</small>

      <label for="cf-phone">Phone (optional)</label>
      <InputText id="cf-phone" v-model="form.phone" inputmode="tel" autocomplete="off" fluid />
      <small v-if="errors.phone" class="problem">{{ errors.phone }}</small>

      <label for="cf-email">Email (optional)</label>
      <InputText id="cf-email" v-model="form.email" type="email" autocomplete="off" fluid />
      <small v-if="errors.email" class="problem">{{ errors.email }}</small>

      <label for="cf-zip">ZIP code (optional)</label>
      <InputText id="cf-zip" v-model="form.zipcode" inputmode="numeric" maxlength="10" autocomplete="off" fluid />
      <small v-if="errors.zipcode" class="problem">{{ errors.zipcode }}</small>

      <label id="cf-lang-label">Languages (optional)</label>
        <MultiSelect
            v-model="form.languages"
            :options="languages"
            display="chip"
            filter
            :selection-limit="MAX_LANGUAGES"
            :show-toggle-all="false"
            placeholder="Choose languages"
            aria-labelledby="cf-lang-label"
            fluid
        />
      <small v-if="errors.languages" class="problem">{{ errors.languages }}</small>

      <div class="row">
        <Button type="submit" :label="client ? 'Save changes' : 'Add client'" :loading="busy" :disabled="!canSave()" />
        <Button type="button" label="Cancel" text severity="secondary" @click="visible = false" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.matches { padding-left: 1.1rem; margin: 0 0 1rem; }
.muted { color: #6b7280; font-size: 0.9rem; }
</style>