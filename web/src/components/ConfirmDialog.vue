<script setup>
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'

defineProps({
  title: { type: String, default: 'Are you sure?' },
  message: { type: String, default: '' },
  confirmLabel: { type: String, default: 'Confirm' },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const visible = defineModel('visible', { type: Boolean, default: false })
defineEmits(['confirm'])
</script>

<template>
  <Dialog v-model:visible="visible" modal :header="title" :style="{ width: '26rem' }">
    <p>{{ message }}</p>
    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    <template #footer>
      <Button label="Cancel" text severity="secondary" :disabled="busy" @click="visible = false" />
      <Button :label="confirmLabel" severity="danger" :loading="busy" @click="$emit('confirm')" />
    </template>
  </Dialog>
</template>