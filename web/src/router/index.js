// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'
import { decide } from './guard'
import LoginView from '../views/LoginView.vue'
import SecurityView from '../views/SecurityView.vue'
import ClientsView from '../views/ClientsView.vue'
import ClientDetailsView from '../views/ClientDetailsView.vue'
import AppointmentsView from '../views/AppointmentsView.vue'
import AppointmentDetailView from '../views/AppointmentDetailView.vue'
import AdminView from '../views/AdminView.vue'
import CallsView from '../views/CallsView.vue'
import DashboardView from '../views/DashboardView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'home', component: DashboardView },
    { path: '/security', name: 'security', component: SecurityView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
    { path: '/clients', name: 'clients', component: ClientsView },
    { path: '/clients/:id(\\d+)', name: 'client', component: ClientDetailsView, props: true },
    { path: '/appointments', name: 'appointments', component: AppointmentsView },
    { path: '/appointments/:id(\\d+)', name: 'appointment', component: AppointmentDetailView, props: true },
    { path: '/admin/:tab?', name: 'admin', component: AdminView, meta: { roles: ['admin', 'manager'] } },
    { path: '/calls', name: 'calls', component: CallsView },
    { path: '/dashboard', redirect: { name: 'home' } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuth()
  if (!auth.ready) await auth.restore()
  return decide(to, auth)
})