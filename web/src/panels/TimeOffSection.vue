<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Connor Bailey -->

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { createTimeOff, deleteTimeOff, listTimeOff, updateTimeOff } from '../schedulingApi'
import {
  addDaysISO, affectedMessage, buildTimeOffPayload, emptyTimeOffForm, formatDateRange, formFromTimeOff,
  navigatorName, schedulingErrorMessage, timeOffProblem, timeOffWho, toLocalISODate,
} from '../lib/scheduling'

const props = defineProps({ techs: { type: Array, default: () => [] } })

const blocks = ref([])
const loading = ref(false)
const showPast = ref(false)
const error = ref('')
const notice = ref({ text: '', severity: 'success' })

const edit = ref({ open: false, id: null, form: emptyTimeOffForm(), busy: false, error: '' })
const removing = ref({ open: false, block: null, busy: false })

const techOptions = computed(() => props.techs.map((t) => ({ tech_id: t.tech_id, label: navigatorName(t) })))

async function load() {
  loading.value = true
  try {
    const today = toLocalISODate(new Date())
    const from = showPast.value ? addDaysISO(today, -365) : today
    blocks.value = await listTimeOff({ from, to: addDaysISO(today, 730) })
  } catch (err) {
    error.value = schedulingErrorMessage(err)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(showPast, load)

function open(block = null) {
  edit.value = {
    open: true, id: block?.time_off_id ?? null, busy: false, error: '',
    form: block ? formFromTimeOff(block) : emptyTimeOffForm(),
  }
}

async function save() {
  const problem = timeOffProblem(edit.value.form)
  if (problem) {
    edit.value.error = problem
    return
  }
  edit.value.busy = true
  edit.value.error = ''
  try {
    const payload = buildTimeOffPayload(edit.value.form)
    const result = edit.value.id ? await updateTimeOff(edit.value.id, payload) : await createTimeOff(payload)
    const warning = affectedMessage(result.affected_bookings)
    notice.value = warning
      ? { text: `Saved. ${warning}`, severity: 'warn' }
      : { text: 'Saved. No booked appointments are affected.', severity: 'success' }
    edit.value.open = false
    await load()
  } catch (err) {
    edit.value.error = schedulingErrorMessage(err)
  } finally {
    edit.value.busy = false
  }
}

async function remove() {
  removing.value.busy = true
  try {
    await deleteTimeOff(removing.value.block.time_off_id)
    notice.value = { text: 'Blocked days removed. Those days are open for booking again.', severity: 'success' }
    removing.value.open = false
    await load()
  } catch (err) {
    error.value = schedulingErrorMessage(err)
    removing.value.open = false
  } finally {
    removing.value.busy = false
  }
}
</script>

<template>
  <section class="timeoff">
    <div class="head">
      <h3>Blocked days</h3>
      <label class="past"><Checkbox v-model="showPast" binary input-id="show-past" /> Show past</label>
      <Button label="Block days" icon="pi pi-plus" @click="open()" />
    </div>
    <p class="muted">
      Close days for holidays, time off or staff development. No appointments can be booked on a blocked
      day, and it appears shaded on the calendar.
    </p>
    <Message v-if="notice.text" :severity="notice.severity" :closable="true" class="mb" @close="notice.text = ''">{{ notice.text }}</Message>
    <Message v-if="error" severity="error" :closable="false" class="mb">{{ error }}</Message>

    <DataTable :value="blocks" :loading="loading" data-key="time_off_id">
      <template #empty>No blocked days{{ showPast ? '' : ' coming up' }}.</template>
      <Column header="Dates">
        <template #body="{ data }">{{ formatDateRange(data.start_date, data.end_date) }}</template>
      </Column>
      <Column header="Applies to">
        <template #body="{ data }">{{ timeOffWho(data, techs) }}</template>
      </Column>
      <Column field="description" header="Description" />
      <Column header="">
        <template #body="{ data }">
          <Button label="Edit" size="small" text @click="open(data)" />
          <Button label="Remove" size="small" text severity="danger" @click="removing = { open: true, block: data, busy: false }" />
        </template>
      </Column>
    </DataTable>

    <Dialog v-model:visible="edit.open" modal :header="edit.id ? 'Edit blocked days' : 'Block days'" :style="{ width: '32rem', maxWidth: '95vw' }">
      <div class="field">
        <label for="to-dates">Day, or first and last day</label>
        <DatePicker v-model="edit.form.dates" input-id="to-dates" selection-mode="range" :manual-input="false" date-format="mm/dd/yy" show-icon fluid />
        <small class="muted">Click one day for a single day, or click a second day to block a range.</small>
      </div>
      <div class="field">
        <label class="inline"><Checkbox v-model="edit.form.all" binary input-id="to-all" /> All navigators</label>
        <small class="muted">Also covers anyone added later.</small>
        <MultiSelect
          v-model="edit.form.tech_ids" :options="techOptions" option-label="label" option-value="tech_id"
          :disabled="edit.form.all" placeholder="Or choose specific navigators" display="chip" fluid
          aria-label="Navigators"
        />
      </div>
      <div class="field">
        <label for="to-desc">Description</label>
        <InputText id="to-desc" v-model="edit.form.description" maxlength="200" placeholder="Christmas, Staff Development Day..." fluid />
      </div>
      <Message v-if="edit.error" severity="error" :closable="false">{{ edit.error }}</Message>
      <template #footer>
        <Button label="Cancel" text severity="secondary" :disabled="edit.busy" @click="edit.open = false" />
        <Button label="Save" :loading="edit.busy" @click="save" />
      </template>
    </Dialog>

    <ConfirmDialog
      v-model:visible="removing.open" title="Remove these blocked days?"
      message="Those days open up for booking again. Existing appointments are not affected."
      confirm-label="Remove" :busy="removing.busy" @confirm="remove"
    />
  </section>
</template>

<style scoped>
.timeoff { margin-top: 2.5rem; }
.head { display: flex; align-items: center; gap: 1rem; }
.head h3 { margin: 0; margin-right: auto; }
.past, .inline { display: flex; align-items: center; gap: 0.4rem; }
.field { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 1rem; }
</style>