<script setup>
import { onMounted, ref } from 'vue'
import { listCalls } from '../callsApi'
import { useAuth } from '../stores/auth'

const auth = useAuth()
const waiting = ref(null)

onMounted(async () => {
  try {
    waiting.value = (await listCalls({ open: true, limit: 1, offset: 0 })).total
  } catch {
    waiting.value = null   // disregarding an error on the home page
  }
})
</script>

<template>
  <h2>Welcome, {{ auth.user?.username }}</h2>
  <p>You're signed in as {{ auth.user?.role }}.</p>
  <p v-if="waiting !== null">
    <router-link :to="{ name: 'calls' }">
      {{ waiting }} call{{ waiting === 1 ? '' : 's' }} waiting for a response
    </router-link>
  </p>
  <p>
    <router-link :to="{ name: 'clients' }">Clients</router-link> ·
    <router-link :to="{ name: 'appointments' }">Appointments</router-link> ·
    <router-link :to="{ name: 'calls' }">Calls</router-link>
  </p>
</template>