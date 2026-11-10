import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'
import { decide } from './guard'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import SecurityView from '../views/SecurityView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'home', component: HomeView },
    { path: '/security', name: 'security', component: SecurityView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuth()
  if (!auth.ready) await auth.restore()
  return decide(to, auth)
})