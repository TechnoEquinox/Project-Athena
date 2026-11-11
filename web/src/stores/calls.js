import { defineStore } from 'pinia'
import { listCalls } from '../callsApi'
import { rangeToParams } from '../lib/appointments'

// Only the newest request may update the table
let sequence = 0

export const useCalls = defineStore('calls', {
  state: () => ({
    mode: 'queue',   // 'queue' = open calls, oldest first. 'all' = every call, newest first.
    status: null,
    techId: null,
    range: null,
    first: 0,
    limit: 25,
    rows: [],
    total: 0,
    loading: false,
    error: '',
  }),
  getters: {
    params(state) {
      const base = { tech_id: state.techId, limit: state.limit, offset: state.first }
      if (state.mode === 'queue') return { open: true, order: 'asc', ...base }
      return { status: state.status, order: 'desc', ...rangeToParams(state.range), ...base }
    },
  },
  actions: {
    setMode(mode) { this.mode = mode; this.first = 0 },
    setStatus(status) { this.status = status; this.first = 0 },
    setTech(id) { this.techId = id; this.first = 0 },
    setRange(range) { this.range = range; this.first = 0 },
    setPage(first) { this.first = first },
    async load() {
      const mine = ++sequence
      this.loading = true
      this.error = ''
      try {
        const data = await listCalls(this.params)
        if (mine !== sequence) return
        this.rows = data.calls
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