<script setup>
import { useAuth } from '../stores/auth'

const auth = useAuth()
</script>

<template>
  <h2>Welcome, {{ auth.user?.username }}</h2>
  <p>You're signed in as {{ auth.user?.role }}.</p>
  <p><router-link :to="{ name: 'clients' }">Find or add a client</router-link></p>
  <p class="muted">Appointments and calls arrive in the next slices.</p>
</template>