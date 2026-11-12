<script setup>
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import {
  ROLE_OPTIONS, adminErrorMessage, buildUserPayload, linkableTechs, roleLabel, techName,
  userFormProblem, userStatus,
} from '../lib/admin'
import { formatDateTime } from '../lib/appointments'
import { useAuth } from '../stores/auth'
import { listTechs } from '../techsApi'
import {
  createUser, deactivateUser, listUsers, reactivateUser, resetPassword, resetTotp, unlockUser,
} from '../usersApi'

const auth = useAuth()
const users = ref([])
const techs = ref([])
const loading = ref(false)
const error = ref('')
const notice = ref('')

const isSelf = (user) => user.user_id === auth.user?.user_id

async function load() {
  loading.value = true
  try {
    const [u, t] = await Promise.all([listUsers(), listTechs({ includeInactive: true })])
    users.value = u
    techs.value = t
  } catch (err) {
    error.value = adminErrorMessage(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)

// ---- add ----
const blankForm = () => ({ username: '', password: '', role: null, tech_id: null })
const add = ref({ open: false, form: blankForm(), busy: false, error: '' })
const techChoices = computed(() => linkableTechs(techs.value))
const addProblem = computed(() => userFormProblem(add.value.form))

function openAdd() {
  notice.value = ''
  add.value = { open: true, form: blankForm(), busy: false, error: '' }
}

async function saveAdd() {
  add.value.busy = true
  add.value.error = ''
  try {
    const user = await createUser(buildUserPayload(add.value.form))
    add.value.open = false
    add.value.form = blankForm()   // never keep a typed password around
    const needs2fa = ['admin', 'manager'].includes(user.role)
    notice.value =
      `Created ${roleLabel(user.role).toLowerCase()} account "${user.username}". ` +
      'Give them the password you set and ask them to change it on the Security page.' +
      (needs2fa ? ' They will be asked to set up two-factor at first sign-in.' : '')
    await load()
  } catch (err) {
    add.value.error = adminErrorMessage(err)
  } finally {
    add.value.busy = false
  }
}

// ---- reset password ----
const reset = ref({ open: false, user: null, pw: '', again: '', busy: false, error: '' })
const resetProblem = computed(() => {
  if (reset.value.pw && reset.value.pw.length < 12) return 'Use at least 12 characters.'
  if (reset.value.again && reset.value.pw !== reset.value.again) return 'The passwords do not match.'
  return ''
})
const resetReady = computed(() => reset.value.pw.length >= 12 && reset.value.pw === reset.value.again)

function openReset(user) {
  notice.value = ''
  reset.value = { open: true, user, pw: '', again: '', busy: false, error: '' }
}

async function saveReset() {
  reset.value.busy = true
  reset.value.error = ''
  try {
    await resetPassword(reset.value.user.user_id, reset.value.pw)
    notice.value =
      `Password reset for "${reset.value.user.username}". They were signed out and any lock was cleared. ` +
      'Give them the new password and ask them to change it.'
    reset.value = { open: false, user: null, pw: '', again: '', busy: false, error: '' }
    await load()
  } catch (err) {
    reset.value.error = adminErrorMessage(err)
  } finally {
    reset.value.busy = false
  }
}

// ---- actions with a confirmation ----
const confirm = ref({ open: false, title: '', message: '', label: '', run: null, busy: false, error: '' })

function ask(title, message, label, run) {
  notice.value = ''
  confirm.value = { open: true, title, message, label, run, busy: false, error: '' }
}

async function runConfirm() {
  confirm.value.busy = true
  confirm.value.error = ''
  try {
    notice.value = await confirm.value.run()
    confirm.value.open = false
    await load()
  } catch (err) {
    confirm.value.error = adminErrorMessage(err)
  } finally {
    confirm.value.busy = false
  }
}

function askDeactivate(user) {
  ask(
    `Deactivate ${user.username}?`,
    'They will be signed out and unable to sign in. Their history stays. You can reactivate them later.',
    'Deactivate',
    async () => {
      await deactivateUser(user.user_id)
      return `Deactivated "${user.username}".`
    },
  )
}

function askResetTotp(user) {
  ask(
    `Reset two-factor for ${user.username}?`,
    'Their authenticator and recovery codes stop working and they are signed out. Admins and managers must set it up again at next sign-in.',
    'Reset 2FA',
    async () => {
      await resetTotp(user.user_id)
      return `Two-factor reset for "${user.username}".`
    },
  )
}

// ---- one-click actions ----
async function quick(fn, user, message) {
  error.value = ''
  notice.value = ''
  try {
    await fn(user.user_id)
    notice.value = message
    await load()
  } catch (err) {
    error.value = adminErrorMessage(err)
  }
}

const unlock = (user) => quick(unlockUser, user, `Unlocked "${user.username}" and signed them out.`)
const reactivate = (user) => quick(reactivateUser, user, `Reactivated "${user.username}".`)

</script>

<template>
  <div class="toolbar">
    <h3 class="grow">Users</h3>
    <Button label="Add user" @click="openAdd" />
  </div>
  <p class="muted">Logins for staff. Each navigator needs a tech record, which you can add on the Techs tab.</p>

  <Message v-if="notice" severity="success" :closable="false" class="mb">{{ notice }}</Message>
  <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

  <DataTable :value="users" :loading="loading" data-key="user_id">
    <Column header="Username">
      <template #body="{ data }">
        {{ data.username }} <span v-if="isSelf(data)" class="muted">(you)</span>
      </template>
    </Column>
    <Column header="Role">
      <template #body="{ data }">{{ roleLabel(data.role) }}</template>
    </Column>
    <Column header="Tech">
      <template #body="{ data }">{{ techName(techs, data.tech_id) || '—' }}</template>
    </Column>
    <Column header="Status">
      <template #body="{ data }">
        <Tag :value="userStatus(data).label" :severity="userStatus(data).severity" />
      </template>
    </Column>
    <Column header="2FA">
      <template #body="{ data }">{{ data.two_factor_enabled ? 'On' : 'Off' }}</template>
    </Column>
    <Column header="Last sign-in">
      <template #body="{ data }">{{ data.last_login_at ? formatDateTime(data.last_login_at) : 'Never' }}</template>
    </Column>
    <Column header="" style="width: 22rem">
      <template #body="{ data }">
        <div class="actions">
          <Button label="Reset password" size="small" text :disabled="isSelf(data)" @click="openReset(data)" />
          <Button
            v-if="data.two_factor_enabled"
            label="Reset 2FA"
            size="small"
            text
            :disabled="isSelf(data)"
            @click="askResetTotp(data)"
          />
          <Button
            v-if="data.locked"
            label="Unlock"
            size="small"
            text
            @click="unlock(data)"
          />
          <Button
            v-if="data.is_active"
            label="Deactivate"
            size="small"
            text
            severity="danger"
            :disabled="isSelf(data)"
            @click="askDeactivate(data)"
          />
          <Button
            v-else
            label="Reactivate"
            size="small"
            text
            @click="reactivate(data)"
          />
        </div>
      </template>
    </Column>
    <template #empty>No users yet.</template>
  </DataTable>

  <Dialog v-model:visible="add.open" modal header="Add user" :style="{ width: '28rem' }">
    <Message v-if="add.error" severity="error" :closable="false" class="mb">{{ add.error }}</Message>
    <form class="form" @submit.prevent="saveAdd">
      <label for="u-name">Username</label>
      <InputText id="u-name" v-model="add.form.username" autocomplete="off" autocapitalize="none" maxlength="64" fluid />

      <label id="u-role-label">Role</label>
      <Select
        v-model="add.form.role"
        :options="ROLE_OPTIONS"
        option-label="label"
        option-value="value"
        placeholder="Choose a role"
        aria-labelledby="u-role-label"
        fluid
      />

      <label id="u-tech-label">
        {{ add.form.role === 'navigator' ? 'Tech record' : 'Tech record (optional)' }}
      </label>
      <Select
        v-model="add.form.tech_id"
        :options="techChoices"
        option-label="label"
        option-value="tech_id"
        :placeholder="techChoices.length ? 'Choose a tech' : 'No techs without a login'"
        :show-clear="add.form.role !== 'navigator'"
        aria-labelledby="u-tech-label"
        fluid
      />
      <small v-if="add.form.role === 'navigator' && !techChoices.length" class="muted">
        Add the tech on the Techs tab first, then come back.
      </small>

      <label for="u-pw">Temporary password (12 characters or more)</label>
      <InputText id="u-pw" v-model="add.form.password" type="password" autocomplete="new-password" fluid />

      <small v-if="addProblem && (add.form.username || add.form.password)" class="problem">{{ addProblem }}</small>

      <div class="row">
        <Button type="submit" label="Create user" :loading="add.busy" :disabled="!!addProblem" />
        <Button type="button" label="Cancel" text severity="secondary" @click="add.open = false" />
      </div>
    </form>
  </Dialog>

  <Dialog v-model:visible="reset.open" modal header="Reset password" :style="{ width: '26rem' }">
    <p v-if="reset.user">
      Set a new password for <strong>{{ reset.user.username }}</strong>. They will be signed out.
    </p>
    <Message v-if="reset.error" severity="error" :closable="false" class="mb">{{ reset.error }}</Message>
    <form class="form" @submit.prevent="saveReset">
      <label for="r-pw">New password (12 characters or more)</label>
      <InputText id="r-pw" v-model="reset.pw" type="password" autocomplete="new-password" fluid />
      <label for="r-again">New password again</label>
      <InputText id="r-again" v-model="reset.again" type="password" autocomplete="new-password" fluid />
      <small v-if="resetProblem" class="problem">{{ resetProblem }}</small>
      <div class="row">
        <Button type="submit" label="Reset password" :loading="reset.busy" :disabled="!resetReady" />
        <Button type="button" label="Cancel" text severity="secondary" @click="reset.open = false" />
      </div>
    </form>
  </Dialog>

  <ConfirmDialog
    v-model:visible="confirm.open"
    :title="confirm.title"
    :message="confirm.message"
    :confirm-label="confirm.label"
    :busy="confirm.busy"
    :error="confirm.error"
    @confirm="runConfirm"
  />
</template>