<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import { useAuth } from '../stores/auth'

const auth = useAuth()
const router = useRouter()
const route = useRoute()

const step = ref('password') // 'password' then 'code'
const username = ref('')
const password = ref('')
const code = ref('')
const useRecovery = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref(route.query.expired ? 'Your session ended. Please sign in again.' : '')

const subtitle = computed(() =>
  step.value === 'password' ? 'Sign in to continue' : 'Two-factor authentication',
)

function describe(err) {
  if (err.status === 0) return err.message
  if (err.status === 400) return 'Enter your username and password.'
  return err.message
}

function startOver(message = '') {
  step.value = 'password'
  code.value = ''
  useRecovery.value = false
  error.value = message
}

async function submitPassword() {
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    const result = await auth.login(username.value.trim(), password.value)
    password.value = ''
    if (result === 'mfa') {
      step.value = 'code'
    } else {
      await router.replace({ name: 'home' })
    }
  } catch (err) {
    error.value = describe(err)
  } finally {
    busy.value = false
  }
}

async function submitCode() {
  error.value = ''
  busy.value = true
  try {
    const value = code.value.trim()
    await auth.submitCode(useRecovery.value ? { recoveryCode: value } : { code: value })
    await router.replace({ name: 'home' })
  } catch (err) {
    if (err.code === 'invalid_code') {
      error.value = 'That code is not valid.'
      code.value = ''
    } else if (err.code === 'mfa_expired') {
      startOver('Your sign-in timed out. Please start again.')
    } else if (err.code === 'invalid_credentials') {
      startOver(err.message)
    } else {
      error.value = describe(err)
    }
  } finally {
    busy.value = false
  }
}

function toggleRecovery() {
  useRecovery.value = !useRecovery.value
  code.value = ''
  error.value = ''
}
</script>

<template>
  <div class="login-wrap">
    <Card class="login-card">
      <template #title>Athena</template>
      <template #subtitle>{{ subtitle }}</template>
      <template #content>
        <Message v-if="notice" severity="info" :closable="false" class="mb">{{ notice }}</Message>
        <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

        <form v-if="step === 'password'" class="form" @submit.prevent="submitPassword">
          <label for="username">Username</label>
          <InputText id="username" v-model="username" autocomplete="username" autocapitalize="none" autofocus fluid />
          <label for="password">Password</label>
          <InputText id="password" v-model="password" type="password" autocomplete="current-password" fluid />
          <Button type="submit" label="Sign in" :loading="busy" :disabled="!username || !password" fluid />
        </form>

        <form v-else class="form" @submit.prevent="submitCode">
          <label :for="useRecovery ? 'recovery' : 'code'">
            {{ useRecovery ? 'Recovery code' : '6-digit code from your authenticator app' }}
          </label>
          <InputText
            :id="useRecovery ? 'recovery' : 'code'"
            v-model="code"
            :inputmode="useRecovery ? 'text' : 'numeric'"
            :autocomplete="useRecovery ? 'off' : 'one-time-code'"
            autocapitalize="none"
            autofocus
            fluid
          />
          <Button type="submit" label="Verify" :loading="busy" :disabled="!code.trim()" fluid />
          <Button
            type="button"
            :label="useRecovery ? 'Use my authenticator app' : 'Use a recovery code'"
            text
            @click="toggleRecovery"
          />
          <Button type="button" label="Start over" text severity="secondary" @click="startOver()" />
        </form>
      </template>
    </Card>
  </div>
</template>