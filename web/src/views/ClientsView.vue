<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ClientFormDialog from '../components/ClientFormDialog.vue'
import { debounce } from '../lib/debounce'
import { formatPhone } from '../lib/forms'
import { useAuth } from '../stores/auth'
import { useClients } from '../stores/clients'

const auth = useAuth()
const clients = useClients()
const route = useRoute()
const router = useRouter()

const search = ref(clients.q)   // kept in memory, so Back from a profile keeps your search
const showCreate = ref(false)

const runSearch = debounce(() => {
  clients.setQuery(search.value)
  clients.load()
}, 300)

watch(search, () => runSearch())
onMounted(() => clients.load())
onBeforeUnmount(() => runSearch.cancel())

function onPage(event) {
  clients.setPage(event.first)
  clients.load()
}

function created(client) {
  router.push({ name: 'client', params: { id: client.client_id } })
}
</script>

<template>
  <div class="toolbar">
    <h2 class="grow">Clients</h2>
    <Button v-if="auth.canWrite" label="Add client" @click="showCreate = true" />
  </div>

  <Message v-if="route.query.deleted" severity="success" :closable="false" class="mb">
    Client deleted.
  </Message>

  <InputText
    v-model="search"
    class="mb"
    placeholder="Search by name, phone or email"
    aria-label="Search clients"
    maxlength="100"
    autofocus
    fluid
  />
  <Message v-if="clients.error" severity="error" :closable="false" class="mb">{{ clients.error }}</Message>

  <DataTable
    :value="clients.rows"
    lazy
    paginator
    :rows="clients.limit"
    :total-records="clients.total"
    :first="clients.first"
    :loading="clients.loading"
    :always-show-paginator="clients.total > clients.limit"
    data-key="client_id"
    @page="onPage"
  >
    <Column header="Name">
      <template #body="{ data }">
        <router-link :to="{ name: 'client', params: { id: data.client_id } }">
          {{ data.last_name }}, {{ data.first_name }}
        </router-link>
      </template>
    </Column>
    <Column header="Phone">
      <template #body="{ data }">{{ formatPhone(data.phone) }}</template>
    </Column>
    <Column field="email" header="Email" />
    <Column field="zipcode" header="ZIP" />
    <template #empty>{{ clients.q ? 'No clients match that search.' : 'No clients yet.' }}</template>
  </DataTable>

  <ClientFormDialog v-model:visible="showCreate" @saved="created" />
</template>