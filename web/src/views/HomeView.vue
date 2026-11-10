<script setup>
import Message from 'primevue/message'
import { useAuth } from '../stores/auth'

const auth = useAuth()
</script>

<template>
  <h2>Welcome, {{ auth.user?.username }}</h2>
  <Message v-if="auth.mfaSetupRequired" severity="warn" :closable="false">
    Your role requires two-factor authentication, and it isn't set up yet. Until it is, most of
    Athena stays locked. The setup screen is the next slice.
  </Message>
  <p v-else>
    You're signed in as {{ auth.user?.role }}. Clients, appointments and calls arrive in the next
    slices.
  </p>
</template>