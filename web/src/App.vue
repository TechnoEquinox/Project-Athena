<script setup>
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import { useAuth } from './stores/auth'

const auth = useAuth()
const router = useRouter()

async function signOut() {
  await auth.logout()
  router.replace({ name: 'login' })
}
</script>

<template>
  <header v-if="auth.isAuthenticated" class="topbar">
    <strong>Athena</strong>
    <router-link to="/clients" class="navlink">Clients</router-link>
    <span class="spacer" />
    <router-link to="/security" class="navlink">Security</router-link>
    <span class="who">{{ auth.user.username }} · {{ auth.user.role }}</span>
    <Button label="Sign out" size="small" severity="secondary" text @click="signOut" />
  </header>
  <main class="content">
    <router-view />
  </main>
</template>