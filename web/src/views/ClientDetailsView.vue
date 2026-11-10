<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import ClientFormDialog from '../components/ClientFormDialog.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import DeviceFormDialog from '../components/DeviceFormDialog.vue'
import { deleteClient, getClient, removeDevice } from '../clientsApi.js'
import { formatDate, formatPhone } from '../lib/forms.js'
import { useAuth } from '../stores/auth.js'

const props = defineProps({ id: { type: String, required: true } })
const auth = useAuth()
const router = useRouter()

const client = ref(null)
const loading = ref(false)
const notFound = ref(false)
const error = ref('')

const showEdit = ref(false)
const showDevice = ref(false)
const editingDevice = ref(null)

const confirm = ref({ open: false, kind: '', device: null, busy: false, error: '' })

async function load() {
  loading.value = true
  error.value = ''
  notFound.value = false
  try {
    client.value = await getClient(props.id)
  } catch (err) {
    client.value = null
    if (err.status === 404) notFound.value = true
    else error.value = err.message
  } finally {
    loading.value = false
  }
}
watch(() => props.id, load, { immediate: true })

function openAddDevice() {
  editingDevice.value = null
  showDevice.value = true
}

function openEditDevice(device) {
  editingDevice.value = device
  showDevice.value = true
}

function askDeleteClient() {
  confirm.value = { open: true, kind: 'client', device: null, busy: false, error: '' }
}

function askRemoveDevice(device) {
  confirm.value = { open: true, kind: 'device', device, busy: false, error: '' }
}

async function runConfirm() {
  confirm.value.busy = true
  confirm.value.error = ''
  try {
    if (confirm.value.kind === 'client') {
      await deleteClient(client.value.client_id)
      router.replace({ name: 'clients', query: { deleted: '1' } })
      return
    }
    await removeDevice(client.value.client_id, confirm.value.device.device_id)
    confirm.value.open = false
    await load()
  } catch (err) {
    confirm.value.error = err.message
  } finally {
    confirm.value.busy = false
  }
}
</script>

<template>
  <p><router-link :to="{ name: 'clients' }">&larr; All clients</router-link></p>

  <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
  <Message v-else-if="notFound" severity="warn" :closable="false">
    This client was not found. They may have been deleted.
  </Message>

  <template v-else-if="client">
    <div class="head">
      <h2>{{ client.first_name }} {{ client.last_name }}</h2>
      <div v-if="auth.canWrite" class="row">
        <Button label="Edit" severity="secondary" @click="showEdit = true" />
        <Button label="Delete" severity="danger" text @click="askDeleteClient" />
      </div>
    </div>

    <Card class="mb">
      <template #content>
        <dl class="facts">
          <dt>Phone</dt><dd>{{ formatPhone(client.phone) || '—' }}</dd>
          <dt>Email</dt><dd>{{ client.email || '—' }}</dd>
          <dt>ZIP code</dt><dd>{{ client.zipcode || '—' }}</dd>
          <dt>Languages</dt><dd>{{ client.languages.length ? client.languages.join(', ') : '—' }}</dd>
          <dt>Added</dt><dd>{{ formatDate(client.created_at) }}</dd>
        </dl>
      </template>
    </Card>

    <div class="toolbar">
      <h3 class="grow">Devices</h3>
      <Button v-if="auth.canWrite" label="Add device" size="small" @click="openAddDevice" />
    </div>
    <DataTable :value="client.devices" data-key="device_id">
      <Column field="device_type" header="Type" />
      <Column field="description" header="Description" />
      <Column v-if="auth.canWrite" header="" style="width: 11rem">
        <template #body="{ data }">
          <div class="row">
            <Button label="Edit" size="small" text @click="openEditDevice(data)" />
            <Button label="Remove" size="small" text severity="danger" @click="askRemoveDevice(data)" />
          </div>
        </template>
      </Column>
      <template #empty>No devices recorded.</template>
    </DataTable>

    <ClientFormDialog v-model:visible="showEdit" :client="client" @saved="(updated) => (client = updated)" />
    <DeviceFormDialog
      v-model:visible="showDevice"
      :client-id="client.client_id"
      :device="editingDevice"
      @saved="load"
    />
    <ConfirmDialog
      v-model:visible="confirm.open"
      :title="confirm.kind === 'client' ? 'Delete this client?' : 'Remove this device?'"
      :message="confirm.kind === 'client'
        ? 'Their devices, appointments and call log entries will be hidden too. An admin can restore them for a limited time.'
        : 'Past appointments will still show this device, marked as removed.'"
      :confirm-label="confirm.kind === 'client' ? 'Delete client' : 'Remove device'"
      :busy="confirm.busy"
      :error="confirm.error"
      @confirm="runConfirm"
    />
  </template>
</template>