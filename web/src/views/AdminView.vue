<script setup>
import { computed, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Tab from 'primevue/tab'
import TabList from 'primevue/tablist'
import Tabs from 'primevue/tabs'
import { adminTabsFor, resolveAdminTab } from '../lib/admin'
import AuditPanel from '../panels/AuditPanel.vue'
import LocationsPanel from '../panels/LocationsPanel.vue'
import RestorePanel from '../panels/RestorePanel.vue'
import TechsPanel from '../panels/TechsPanel.vue'
import UsersPanel from '../panels/UsersPanel.vue'
import { useAuth } from '../stores/auth'

const PANELS = {
  users: UsersPanel,
  techs: TechsPanel,
  locations: LocationsPanel,
  restore: RestorePanel,
  audit: AuditPanel,
}

const auth = useAuth()
const route = useRoute()
const router = useRouter()

const tabs = computed(() => adminTabsFor(auth.user?.role))
const current = computed(() => resolveAdminTab(auth.user?.role, route.params.tab))

// /admin and tabs this role can't see are tidied up to the right address.
// The route-name check stops this from fighting a navigation away from the page.
watchEffect(() => {
  if (route.name === 'admin' && current.value && route.params.tab !== current.value) {
    router.replace({ name: 'admin', params: { tab: current.value } })
  }
})

function select(key) {
  if (key !== current.value) router.push({ name: 'admin', params: { tab: key } })
}
</script>

<template>
  <h2>Admin</h2>
  <Tabs v-if="current" :value="current" @update:value="select">
    <TabList>
      <Tab v-for="t in tabs" :key="t.key" :value="t.key">{{ t.label }}</Tab>
    </TabList>
  </Tabs>
  <div v-if="current" class="admin-body">
    <component :is="PANELS[current]" :key="current" />
  </div>
</template>