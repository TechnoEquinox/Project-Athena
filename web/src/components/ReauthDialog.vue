<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import { buildCheck } from '../lib/server'

const props = defineProps({
  title: { type: String, default: 'Confirm it is you' },
  message: { type: String, default: '' },
  confirmLabel: { type: String, default: 'Confirm' },
  needsCode: { type: Boolean, default: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const visible = defineModel('visible', { type: Boolean, default: false })
const emit = defineEmits(['confirm'])

const password = ref('')
const second = ref('')
const recovery = ref(false)

// Start clean every time the box opens, so nothing typed earlier lingers.
watch(visible, (open) => {
  if (open) {
    password.value = ''
    second.value = ''
    recovery.value = false
  }
})

const ready = computed(() => !!password.value && (!props.needsCode || !!second.value.trim()))

function submit() {
  if (!ready.value || props.busy) return
  emit('confirm', buildCheck(password.value, props.needsCode ? second.value : '', recovery.value))
}
</script>

<template>
  <Dialog v-model:visible="visible" modal :header="title" :style="{ width: '28rem' }" :closable="!busy">
    <form class="form" @submit.prevent="submit">
      <p>{{ message }}</p>
      <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

      <label for="reauth-pw">Your password</label>
      <InputText id="reauth-pw" v-model="password" type="password" autocomplete="current-password" fluid autofocus />

      <template v-if="needsCode">
        <label for="reauth-second">
          {{ recovery ? 'One of your recovery codes' : 'The 6-digit code from your authenticator app' }}
        </label>
        <InputText id="reauth-second" v-model="second" autocomplete="off"
                   :inputmode="recovery ? 'text' : 'numeric'" fluid />
        <Button type="button" size="small" text severity="secondary"
                :label="recovery ? 'Use my authenticator app instead' : 'Use a recovery code instead'"
                @click="recovery = !recovery; second = ''" />
      </template>
    </form>
    <template #footer>
      <Button label="Cancel" text severity="secondary" :disabled="busy" @click="visible = false" />
      <Button :label="confirmLabel" severity="danger" :loading="busy" :disabled="!ready" @click="submit" />
    </template>
  </Dialog>
</template>
