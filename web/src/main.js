import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'
import App from './App.vue'
import { router } from './router'
import { useAuth } from './stores/auth'
import { setUnauthorizedHandler } from './api'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: 'none' } } })
app.use(router)

// A 401 on a normal request means the session ended (idle timeout, another login, or deactivation)
setUnauthorizedHandler(() => {
  const auth = useAuth()
  if (auth.user) {
    auth.clear()
    router.replace({ name: 'login', query: { expired: '1' } })
  }
})

app.mount('#app')