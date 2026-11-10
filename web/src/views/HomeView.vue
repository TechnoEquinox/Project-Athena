<script setup>
import { useAuth } from '../stores/auth'

const auth = useAuth()
</script>

<template>
  <h2>Welcome, {{ auth.user?.username }}</h2>
  <p>
    You're signed in as {{ auth.user?.role }}. Clients, appointments and calls arrive in the next
    slices.
  </p>
</template>