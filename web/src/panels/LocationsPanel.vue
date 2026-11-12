<script setup>
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import {
  createLocation, deactivateLocation, listLocations, reactivateLocation, renameLocation,
} from '../locationsApi.js'

const rows = ref([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

async function load() {
  loading.value = true
  try {
    rows.value = await listLocations({ includeInactive: true })
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
onMounted(load)

const newName = ref('')
const adding = ref(false)

async function add() {
  error.value = ''
  notice.value = ''
  adding.value = true
  try {
    const loc = await createLocation(newName.value.trim())
    newName.value = ''
    notice.value = `Added ${loc.name}.`
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    adding.value = false
  }
}

const rename = ref({ open: false, id: null, name: '', busy: false, error: '' })

function openRename(loc) {
  rename.value = { open: true, id: loc.location_id, name: loc.name, busy: false, error: '' }
}

async function saveRename() {
  rename.value.busy = true
  rename.value.error = ''
  try {
    await renameLocation(rename.value.id, rename.value.name.trim())
    rename.value.open = false
    await load()
  } catch (err) {
    rename.value.error = err.message
  } finally {
    rename.value.busy = false
  }
}

const removing = ref({ open: false, location: null, busy: false, error: '' })

function askRemove(loc) {
  removing.value = { open: true, location: loc, busy: false, error: '' }
}

async function confirmRemove() {
  removing.value.busy = true
  removing.value.error = ''
  try {
    await deactivateLocation(removing.value.location.location_id)
    removing.value.open = false
    await load()
  } catch (err) {
    removing.value.error = err.message
  } finally {
    removing.value.busy = false
  }
}

async function reactivate(loc) {
  error.value = ''
  try {
    await reactivateLocation(loc.location_id)
    await load()
  } catch (err) {
    error.value = err.message
  }
}
</script>

<template>
  <h3>Locations</h3>
  <p class="muted">Where appointments happen. Removing a location hides it from new appointments, and old appointments keep it.</p>

  <Message v-if="notice" severity="success" :closable="false" class="mb">{{ notice }}</Message>
  <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

  <form class="row mb" @submit.prevent="add">
    <InputText v-model="newName" placeholder="New location, e.g. Senior Center" maxlength="100" aria-label="New location name" />
    <Button type="submit" label="Add location" :loading="adding" :disabled="!newName.trim()" />
  </form>

  <DataTable :value="rows" :loading="loading" data-key="location_id">
    <Column field="name" header="Name" />
    <Column header="Status" style="width: 8rem">
      <template #body="{ data }">
        <Tag :value="data.is_active ? 'In use' : 'Removed'" :severity="data.is_active ? 'success' : 'secondary'" />
      </template>
    </Column>
    <Column header="" style="width: 14rem">
      <template #body="{ data }">
        <div class="row">
          <Button label="Rename" size="small" text @click="openRename(data)" />
          <Button v-if="data.is_active" label="Remove" size="small" text severity="danger" @click="askRemove(data)" />
          <Button v-else label="Reactivate" size="small" text @click="reactivate(data)" />
        </div>
      </template>
    </Column>
    <template #empty>
      No locations yet. Add the places where appointments happen, such as the library and the senior center.
    </template>
  </DataTable>

  <Dialog v-model:visible="rename.open" modal header="Rename location" :style="{ width: '26rem' }">
    <Message v-if="rename.error" severity="error" :closable="false" class="mb">{{ rename.error }}</Message>
    <form class="form" @submit.prevent="saveRename">
      <label for="loc-name">Name</label>
      <InputText id="loc-name" v-model="rename.name" maxlength="100" fluid />
      <p class="muted">Renaming changes the name on every past appointment too, which is right for fixing a typo.</p>
      <div class="row">
        <Button type="submit" label="Save" :loading="rename.busy" :disabled="!rename.name.trim()" />
        <Button type="button" label="Cancel" text severity="secondary" @click="rename.open = false" />
      </div>
    </form>
  </Dialog>

  <ConfirmDialog
    v-model:visible="removing.open"
    title="Remove this location?"
    :message="`${removing.location?.name ?? ''} will disappear from the choices for new appointments. Past appointments keep it, and you can reactivate it later.`"
    confirm-label="Remove"
    :busy="removing.busy"
    :error="removing.error"
    @confirm="confirmRemove"
  />
</template>