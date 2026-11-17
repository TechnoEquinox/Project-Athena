<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import QRCode from 'qrcode'
import Button from 'primevue/button'
import Card from 'primevue/card'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import RecoveryCodesDialog from '../components/RecoveryCodesDialog.vue'
import { useAuth } from '../stores/auth'

const auth = useAuth()
const router = useRouter()

const enabled = computed(() => !!auth.user?.two_factor_enabled)
const roleRequires2fa = computed(() => ['admin', 'manager'].includes(auth.user?.role))

const error = ref('')
const notice = ref('')
const busy = ref(false)

function show(err) {
  error.value = err.code === 'account_locked' ? 'Too many wrong attempts. Your account is locked.' : err.message
  if (err.code === 'account_locked') router.replace({ name: 'login' })
}

// ---- change password ----
const pw = ref({ current: '', next: '', again: '' })
const pwProblem = computed(() => {
  if (pw.value.next && pw.value.next.length < 12) return 'Use at least 12 characters.'
  if (pw.value.again && pw.value.next !== pw.value.again) return 'The new passwords do not match.'
  return ''
})
const pwReady = computed(
  () => pw.value.current && pw.value.next.length >= 12 && pw.value.next === pw.value.again,
)

async function changePassword() {
  error.value = notice.value = ''
  busy.value = true
  try {
    await auth.changePassword(pw.value.current, pw.value.next)
    pw.value = { current: '', next: '', again: '' }
    notice.value = 'Password changed. Other sessions were signed out.'
  } catch (err) {
    if (err.code === 'current_password_incorrect') error.value = 'Your current password is wrong.'
    else if (err.code === 'password_unchanged') error.value = 'Choose a password you have not used just now.'
    else show(err)
  } finally {
    busy.value = false
  }
}

// ---- enrollment ----
const enroll = ref({ step: 'idle', password: '', secret: '', qr: '', code: '' })
const codes = ref([])
const showCodes = ref(false)

async function beginEnroll() {
  error.value = notice.value = ''
  busy.value = true
  try {
    const data = await auth.startTotpSetup(enroll.value.password)
    enroll.value.secret = data.secret
    enroll.value.qr = await QRCode.toDataURL(data.otpauth_uri, { margin: 1, width: 220 })
    enroll.value.password = ''
    enroll.value.step = 'scan'
  } catch (err) {
    if (err.code === 'current_password_incorrect') error.value = 'Your password is wrong.'
    else if (err.code === 'already_enabled') error.value = 'Two-factor is already on.'
    else show(err)
  } finally {
    busy.value = false
  }
}

async function finishEnroll() {
  error.value = ''
  busy.value = true
  try {
    codes.value = await auth.enableTotp(enroll.value.code.trim())
    showCodes.value = true
    enroll.value = { step: 'idle', password: '', secret: '', qr: '', code: '' }
  } catch (err) {
    error.value = err.code === 'invalid_code' ? 'That code is not valid. Wait for the next one and try again.' : err.message
    enroll.value.code = ''
  } finally {
    busy.value = false
  }
}

function cancelEnroll() {
  enroll.value = { step: 'idle', password: '', secret: '', qr: '', code: '' }
}

function afterCodes() {
  if (!auth.mfaSetupRequired) router.replace({ name: 'home' })
}

// ---- disable and regenerate ----
const manage = ref({ mode: '', password: '', second: '', recovery: false })

function openManage(mode) {
  manage.value = { mode, password: '', second: '', recovery: false }
  error.value = notice.value = ''
}

async function submitManage() {
  error.value = ''
  busy.value = true
  const m = manage.value
  const second = m.recovery ? { recoveryCode: m.second.trim() } : { code: m.second.trim() }
  try {
    if (m.mode === 'disable') {
      await auth.disableTotp(m.password, second)
      notice.value = 'Two-factor is now off.'
    } else {
      codes.value = await auth.regenerateRecoveryCodes(m.password, second)
      showCodes.value = true
    }
    manage.value = { mode: '', password: '', second: '', recovery: false }
  } catch (err) {
    if (err.code === 'current_password_incorrect') error.value = 'Your password is wrong.'
    else if (err.code === 'invalid_code') error.value = 'That code is not valid.'
    else if (err.code === 'totp_required_for_role') error.value = 'Your role requires two-factor, so it cannot be turned off.'
    else show(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <h2>Security</h2>
  <Message v-if="auth.mfaSetupRequired" severity="warn" :closable="false" class="mb">
    Your role requires two-factor authentication. Turn it on below to continue.
  </Message>
  <Message v-if="notice" severity="success" :closable="false" class="mb">{{ notice }}</Message>
  <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

  <Card class="mb">
    <template #title>Two-factor authentication</template>
    <template #content>
      <p>Status: <strong>{{ enabled ? 'On' : 'Off' }}</strong></p>

      <!-- not enabled -->
      <template v-if="!enabled">
        <form v-if="enroll.step === 'idle'" class="form narrow" @submit.prevent="beginEnroll">
          <label for="enroll-pw">Confirm your password to begin</label>
          <InputText id="enroll-pw" v-model="enroll.password" type="password" autocomplete="current-password" fluid />
          <Button type="submit" label="Set up two-factor" :loading="busy" :disabled="!enroll.password" />
        </form>

        <div v-else class="form narrow">
          <p>1. Scan this code with an authenticator app (Google Authenticator, Authy, 1Password and similar).</p>
          <img :src="enroll.qr" alt="QR code for your authenticator app" width="220" height="220" />
          <p class="muted">Cannot scan? Enter this key manually, time-based:</p>
          <code>{{ enroll.secret }}</code>
          <form class="form" @submit.prevent="finishEnroll">
            <label for="enroll-code">2. Enter the 6-digit code the app shows</label>
            <InputText id="enroll-code" v-model="enroll.code" inputmode="numeric" autocomplete="one-time-code" fluid />
            <Button type="submit" label="Turn on" :loading="busy" :disabled="!enroll.code.trim()" />
            <Button type="button" label="Cancel" text severity="secondary" @click="cancelEnroll" />
          </form>
        </div>
      </template>

      <!-- enabled -->
      <template v-else>
        <div v-if="!manage.mode" class="row">
          <Button label="New recovery codes" severity="secondary" @click="openManage('codes')" />
          <Button
            v-if="!roleRequires2fa"
            label="Turn off"
            severity="danger"
            text
            @click="openManage('disable')"
          />
        </div>
        <form v-else class="form narrow" @submit.prevent="submitManage">
          <p v-if="manage.mode === 'codes'" class="muted">This replaces your old recovery codes.</p>
          <label for="m-pw">Your password</label>
          <InputText id="m-pw" v-model="manage.password" type="password" autocomplete="current-password" fluid />
          <label for="m-second">
            {{ manage.recovery ? 'A recovery code' : '6-digit authenticator code' }}
          </label>
          <InputText id="m-second" v-model="manage.second" autocomplete="off" fluid />
          <Button
            type="submit"
            :label="manage.mode === 'disable' ? 'Turn off two-factor' : 'Create new codes'"
            :severity="manage.mode === 'disable' ? 'danger' : undefined"
            :loading="busy"
            :disabled="!manage.password || !manage.second.trim()"
          />
          <Button
            type="button"
            :label="manage.recovery ? 'Use my authenticator app' : 'Use a recovery code'"
            text
            @click="manage.recovery = !manage.recovery; manage.second = ''"
          />
          <Button type="button" label="Cancel" text severity="secondary" @click="manage.mode = ''" />
        </form>
      </template>
    </template>
  </Card>

  <Card v-if="!auth.mfaSetupRequired">
    <template #title>Change password</template>
    <template #content>
      <form class="form narrow" @submit.prevent="changePassword">
        <label for="pw-current">Current password</label>
        <InputText id="pw-current" v-model="pw.current" type="password" autocomplete="current-password" fluid />
        <label for="pw-new">New password (12 characters or more)</label>
        <InputText id="pw-new" v-model="pw.next" type="password" autocomplete="new-password" fluid />
        <label for="pw-again">New password again</label>
        <InputText id="pw-again" v-model="pw.again" type="password" autocomplete="new-password" fluid />
        <small v-if="pwProblem" class="problem">{{ pwProblem }}</small>
        <Button type="submit" label="Change password" :loading="busy" :disabled="!pwReady" />
      </form>
    </template>
  </Card>

  <RecoveryCodesDialog v-model:visible="showCodes" :codes="codes" @update:visible="(v) => !v && afterCodes()" />
</template>

<style scoped>
.narrow { max-width: 24rem; }
.row { display: flex; gap: 0.5rem; align-items: center; }
.muted { color: #6b7280; font-size: 0.9rem; }
.problem { color: #b91c1c; }
code { background: #f3f4f6; padding: 0.4rem 0.6rem; border-radius: 6px; word-break: break-all; }
</style>