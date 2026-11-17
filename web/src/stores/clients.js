// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { defineStore } from 'pinia'
import { listClients } from '../clientsApi'

// Only the newest request may update the table, so a slow answer to an old search can't overwrite a newer one
let sequence = 0

export const useClients = defineStore('clients', {
  state: () => ({ q: '', first: 0, limit: 25, rows: [], total: 0, loading: false, error: '' }),
  actions: {
    setQuery(q) {
      this.q = q
      this.first = 0
    },
    setPage(first) {
      this.first = first
    },
    async load() {
      const mine = ++sequence
      this.loading = true
      this.error = ''
      try {
        const data = await listClients({ q: this.q.trim(), limit: this.limit, offset: this.first })
        if (mine !== sequence) return
        this.rows = data.clients
        this.total = data.total
      } catch (err) {
        if (mine !== sequence) return
        this.error = err.message
      } finally {
        if (mine === sequence) this.loading = false
      }
    },
  },
})