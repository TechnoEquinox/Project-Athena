<script setup>
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { adminErrorMessage, buildTechPayload, emptyTechForm, roleLabel, showDate } from '../lib/admin'
import { fieldErrorFrom } from '../lib/forms'
import { createTech, deactivateTech, listTechs, reactivateTech, updateTech } from '../techsApi'

const techs = ref([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

async function load() {
  loading.value = true
  try {
    techs.value = await listTechs({ includeInactive: true })
  } catch (err) {
    error.value = adminErrorMessage(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)

// ---- add and edit ----
const dlg = ref({ open: false, tech: null, form: emptyTechForm(), errors: {}, error: '', matches: [], busy: false })

function openDialog(tech = null) {
  notice.value = ''
  dlg.value = { open: true, tech, form: emptyTechForm(tech), errors: {}, error: '', matches: [], busy: false }
}

async function save(force = false) {
  const d = dlg.value
  d.error = ''
  d.errors = {}
  const payload = buildTechPayload(d.form, d.tech)
  if (d.tech && Object.keys(payload).length === 0) {
    d.open = false
    return
  }
  d.busy = true
  try {
    if (d.tech) await updateTech(d.tech.tech_id, payload)
    else await createTech(payload, { force })
    notice.value = d.tech ? 'Tech updated.' : 'Tech added.'
    d.open = false
    await load()
  } catch (err) {
    const field = fieldErrorFrom(err)
    if (err.code === 'possible_duplicate') d.matches = err.body.matches ?? []
    else if (field) d.errors = { [field.field]: field.message }
    else d.error = adminErrorMessage(err)
  } finally {
    d.busy = false
  }
}

// ---- deactivate and reactivate ----
const confirm = ref({ open: false, tech: null, busy: false, error: '' })

function askDeactivate(tech) {
  notice.value = ''
  confirm.value = { open: true, tech, busy: false, error: '' }
}

async function runDeactivate() {
  const tech = confirm.value.tech
  confirm.value.busy = true
  confirm.value.error = ''
  try {
    const result = await deactivateTech(tech.tech_id)
    confirm.value.open = false
    notice.value =
      `Deactivated ${tech.first_name} ${tech.last_name}.` +
      (result.loginDeactivated ? ' Their login was deactivated too and they were signed out.' : '')
    await load()
  } catch (err) {
    confirm.value.error = adminErrorMessage(err)
  } finally {
    confirm.value.busy = false
  }
}

async function reactivate(tech) {
  error.value = ''
  notice.value = ''
  try {
    await reactivateTech(tech.tech_id)
    notice.value =
      `Reactivated ${tech.first_name} ${tech.last_name}.` +
      (tech.login_role ? ' Their login is still inactive. Reactivate it on the Users tab.' : '')
    await load()
  } catch (err) {
    error.value = adminErrorMessage(err)
  }
}
</script>

<template>
  <div class="toolbar">
    <h3 class="grow">Techs</h3>
    <Button label="Add tech" @click="openDialog()" />
  </div>
  <p class="muted">
    Everyone who takes appointments and calls. A tech is not a login, so create the login on the Users tab.
    Techs are deactivated, never deleted, so their history stays.
  </p>

  <Message v-if="notice" severity="success" :closable="false" class="mb">{{ notice }}</Message>
  <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

  <DataTable :value="techs" :loading="loading" data-key="tech_id">
    <Column header="Name">
      <template #body="{ data }">{{ data.last_name }}, {{ data.first_name }}</template>
    </Column>
    <Column header="Started">
      <template #body="{ data }">{{ showDate(data.start_date) }}</template>
    </Column>
    <Column header="Login">
      <template #body="{ data }">{{ data.login_role ? roleLabel(data.login_role) : '—' }}</template>
    </Column>
    <Column header="Status" style="width: 8rem">
      <template #body="{ data }">
        <Tag :value="data.is_active ? 'In use' : 'Inactive'" :severity="data.is_active ? 'success' : 'secondary'" />
      </template>
    </Column>
    <Column header="" style="width: 15rem">
      <template #body="{ data }">
        <div class="actions">
          <Button label="Edit" size="small" text @click="openDialog(data)" />
          <Button v-if="data.is_active" label="Deactivate" size="small" text severity="danger" @click="askDeactivate(data)" />
          <Button v-else label="Reactivate" size="small" text @click="reactivate(data)" />
        </div>
      </template>
    </Column>
    <template #empty>No techs yet.</template>
  </DataTable>

  <Dialog v-model:visible="dlg.open" modal :header="dlg.tech ? 'Edit tech' : 'Add tech'" :style="{ width: '28rem' }">
    <Message v-if="dlg.error" severity="error" :closable="false" class="mb">{{ dlg.error }}</Message>

    <div v-if="dlg.matches.length">
      <Message severity="warn" :closable="false" class="mb">A tech with this name already exists:</Message>
      <ul class="matches">
        <li v-for="m in dlg.matches" :key="m.tech_id">
          {{ m.last_name }}, {{ m.first_name }}
          <span class="muted">
            · {{ m.is_active ? 'in use' : 'inactive' }}{{ m.login_role ? ` · ${roleLabel(m.login_role)} login` : '' }}
          </span>
        </li>
      </ul>
      <p class="muted">If this is the same person returning, reactivate their record instead.</p>
      <div class="row">
        <Button label="Add anyway" severity="warn" :loading="dlg.busy" @click="save(true)" />
        <Button label="Go back and edit" text severity="secondary" @click="dlg.matches = []" />
      </div>
    </div>

    <form v-else class="form" @submit.prevent="save(false)">
      <label for="t-first">First name</label>
      <InputText id="t-first" v-model="dlg.form.first_name" autocomplete="off" fluid />
      <small v-if="dlg.errors.first_name" class="problem">{{ dlg.errors.first_name }}</small>

      <label for="t-last">Last name</label>
      <InputText id="t-last" v-model="dlg.form.last_name" autocomplete="off" fluid />
      <small v-if="dlg.errors.last_name" class="problem">{{ dlg.errors.last_name }}</small>

      <label for="t-start">Start date</label>
      <DatePicker v-model="dlg.form.start_date" input-id="t-start" show-icon fluid />
      <small v-if="dlg.errors.start_date" class="problem">{{ dlg.errors.start_date }}</small>

      <div class="row">
        <Button
          type="submit"
          :label="dlg.tech ? 'Save changes' : 'Add tech'"
          :loading="dlg.busy"
          :disabled="!dlg.form.first_name.trim() || !dlg.form.last_name.trim() || !dlg.form.start_date"
        />
        <Button type="button" label="Cancel" text severity="secondary" @click="dlg.open = false" />
      </div>
    </form>
  </Dialog>

  <ConfirmDialog
    v-model:visible="confirm.open"
    title="Deactivate this tech?"
    :message="`${confirm.tech?.first_name ?? ''} ${confirm.tech?.last_name ?? ''} will no longer appear when logging new appointments and calls. If they have a login, it is deactivated too and they are signed out. Their history stays.`"
    confirm-label="Deactivate"
    :busy="confirm.busy"
    :error="confirm.error"
    @confirm="runDeactivate"
  />
</template>

<style scoped>
.matches { padding-left: 1.1rem; margin: 0 0 0.75rem; }
</style>