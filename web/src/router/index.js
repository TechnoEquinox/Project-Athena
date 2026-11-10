import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'home', component: HomeView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuth()
  if (!auth.ready) await auth.restore()
  if (to.meta.public) return auth.isAuthenticated ? { name: 'home' } : true
  return auth.isAuthenticated ? true : { name: 'login' }
})