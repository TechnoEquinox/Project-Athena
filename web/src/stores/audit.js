// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { defineStore } from 'pinia'
import { listAudit } from '../auditApi'

const PAGE = 50

// Only the newest request may change the list, so a slow page can't land on top of a newer view
let sequence = 0

export const useAudit = defineStore('audit', {
  state: () => ({ action: null, entries: [], nextBeforeId: null, loading: false, error: '' }),
  actions: {
    setAction(action) {
      this.action = action
    },
    async load() {
      const mine = ++sequence
      this.loading = true
      this.error = ''
      try {
        const data = await listAudit({ action: this.action, limit: PAGE })
        if (mine !== sequence) return
        this.entries = data.entries
        this.nextBeforeId = data.next_before_id
      } catch (err) {
        if (mine !== sequence) return
        this.error = err.message
      } finally {
        if (mine === sequence) this.loading = false
      }
    },
    async more() {
      if (this.loading || this.nextBeforeId == null) return
      const mine = ++sequence
      this.loading = true
      this.error = ''
      try {
        const data = await listAudit({ action: this.action, before_id: this.nextBeforeId, limit: PAGE })
        if (mine !== sequence) return
        this.entries = [...this.entries, ...data.entries]
        this.nextBeforeId = data.next_before_id
      } catch (err) {
        if (mine !== sequence) return
        this.error = err.message
      } finally {
        if (mine === sequence) this.loading = false
      }
    },
  },
})