<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import Button from 'primevue/button'
import Card from 'primevue/card'

defineProps({ busy: { type: Boolean, default: false } })
defineEmits(['run'])
</script>

<template>
  <Card>
    <template #title>Restart and clean up</template>
    <template #content>
      <div class="action">
        <Button label="Restart Athena" severity="secondary" icon="pi pi-sync" :disabled="busy"
                @click="$emit('run', 'restart-services')" />
        <p class="muted">
          Restarts the database, web app and web server. Everyone stays signed in, but pages may
          fail for about 30 seconds. Try this first if Athena seems stuck.
        </p>
      </div>
      <div class="action">
        <Button label="Restart the server" severity="danger" icon="pi pi-power-off" :disabled="busy"
                @click="$emit('run', 'reboot')" />
        <p class="muted">
          Restarts the whole computer. Athena is unavailable for a minute or two and comes back by itself.
          Do this after updates that ask for it.
        </p>
      </div>
      <div class="action">
        <Button label="Clean up unused Docker files" severity="secondary" icon="pi pi-trash" :disabled="busy"
                @click="$emit('run', 'docker-cleanup')" />
        <p class="muted">
          Frees disk space by removing old leftover build files. Your data, backups and running services
          are not touched.
        </p>
      </div>
    </template>
  </Card>
</template>
