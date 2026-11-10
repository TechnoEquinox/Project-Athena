import { defineStore } from 'pinia'
import { listAppointments } from '../appointmentsApi'
import { rangeToParams, yearRange } from '../lib/appointments'

// Only the newest request may update the table
let sequence = 0

export const useAppointments = defineStore('appointments', {
  state: () => ({
    range: yearRange(new Date()),
    techId: null,
    locationId: null,
    first: 0,
    limit: 25,
    rows: [],
    total: 0,
    loading: false,
    error: '',
  }),
  actions: {
    setRange(range) { this.range = range; this.first = 0 },
    setTech(id) { this.techId = id; this.first = 0 },
    setLocation(id) { this.locationId = id; this.first = 0 },
    setPage(first) { this.first = first },
    async load() {
      const mine = ++sequence
      this.loading = true
      this.error = ''
      try {
        const data = await listAppointments({
          ...rangeToParams(this.range),
          tech_id: this.techId,
          location_id: this.locationId,
          limit: this.limit,
          offset: this.first,
        })
        if (mine !== sequence) return
        this.rows = data.appointments
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