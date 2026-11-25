<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

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
    <router-link :to="{ name: 'home' }" class="brand">Athena</router-link>
    <router-link :to="{ name: 'home' }" class="navlink">Dashboard</router-link>
    <router-link to="/clients" class="navlink">Clients</router-link>
    <router-link to="/calendar" class="navlink">Calendar</router-link>
    <router-link to="/appointments" class="navlink">Appointments</router-link>
    <router-link to="/calls" class="navlink">Calls</router-link>
    <router-link v-if="auth.canViewAdmin" to="/admin" class="navlink">Admin</router-link>
    <span class="spacer" />
    <router-link to="/security" class="navlink">Security</router-link>
    <span class="who">{{ auth.user.username }} · {{ auth.user.role }}</span>
    <Button label="Sign out" size="small" severity="secondary" text @click="signOut" />
  </header>
  <main class="content">
    <router-view />
  </main>
</template>