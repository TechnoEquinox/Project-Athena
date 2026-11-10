<script setup>
import { ref, watch } from 'vue'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Dialog from 'primevue/dialog'

const props = defineProps({ codes: { type: Array, default: () => [] } })
const visible = defineModel('visible', { type: Boolean, default: false })
const saved = ref(false)
const copied = ref(false)

watch(visible, (open) => {
  if (open) {
    saved.value = false
    copied.value = false
  }
})

const text = () => props.codes.join('\n')

async function copy() {
  try {
    await navigator.clipboard.writeText(text())
    copied.value = true
  } catch {
    copied.value = false   // clipboard needs a secure context; download still works
  }
}

function download() {
  const url = URL.createObjectURL(new Blob([text() + '\n'], { type: 'text/plain' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'athena-recovery-codes.txt'
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="Save your recovery codes"
    :closable="false"
    :style="{ width: '28rem' }"
  >
    <p>
      Each code works once if you lose your authenticator. <strong>This is the only time they are
      shown.</strong> Store them in your password manager.
    </p>
    <pre class="codes">{{ codes.join('\n') }}</pre>
    <div class="row">
      <Button label="Copy" size="small" severity="secondary" @click="copy" />
      <Button label="Download" size="small" severity="secondary" @click="download" />
      <span v-if="copied" class="muted">Copied</span>
    </div>
    <div class="row">
      <Checkbox v-model="saved" binary input-id="saved" />
      <label for="saved">I have saved these codes somewhere safe</label>
    </div>
    <template #footer>
      <Button label="Done" :disabled="!saved" @click="visible = false" />
    </template>
  </Dialog>
</template>

<style scoped>
.codes { background: #f3f4f6; padding: 0.75rem; border-radius: 6px; font-size: 1rem; line-height: 1.6; }
.row { display: flex; align-items: center; gap: 0.5rem; margin-top: 0.75rem; }
.muted { color: #6b7280; font-size: 0.85rem; }
</style>