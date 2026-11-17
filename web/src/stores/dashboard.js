// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Connor Bailey

import { defineStore } from 'pinia'
import { formatYmd } from '../lib/admin'
import { matchPreset, presetOptions, presetRange, rangeProblem } from '../lib/dashboard'
import {
  getAppointmentsReport, getCallsReport, getCounters, getDevicesReport, getLocationsReport, getZipsReport, getLanguagesReport
} from '../statsApi'

// Only the newest request may update the charts
let sequence = 0

export const useDashboard = defineStore('dashboard', {
  state: () => ({
    today: null,
    timezone: '',
    fiscalStartMonth: 7,
    counters: null,
    countersError: '',
    preset: 'thisYear',
    from: null,
    to: null,
    interval: 'month',
    mode: 'total',
    appointments: null,
    calls: null,
    locations: null,
    devices: null,
    zips: null,
    languages: null,
    loading: false,
    error: '',
    rangeError: '',
  }),
  actions: {
    async init() {
      try {
        const data = await getCounters()
        this.counters = data
        this.today = data.today
        this.timezone = data.timezone
        this.fiscalStartMonth = data.fiscal_year_start_month
        this.countersError = ''
      } catch (err) {
        this.countersError = err.message
        if (!this.today) this.today = formatYmd(new Date())   // good enough to pick a default range
      }
      if (!this.from) {
        const range = presetRange('thisYear', this.today, this.fiscalStartMonth)
        this.from = range.from
        this.to = range.to
        this.preset = 'thisYear'
      }
      await this.loadReports()
    },
    async loadReports() {
      const mine = ++sequence
      this.loading = true
      this.error = ''
      const range = { from: this.from, to: this.to }
      const grouped = { ...range, interval: this.interval }
      try {
          const [appointments, calls, locations, devices, zips, languages] = await Promise.all([
          getAppointmentsReport(grouped),
          getCallsReport(grouped),
          getLocationsReport(grouped),
          getDevicesReport(range),
          getZipsReport(range),
          getLanguagesReport(range),
        ])
        
        if (mine !== sequence) return
        this.$patch({ appointments, calls, locations, devices, zips, languages })
        
        if (mine !== sequence) return
        this.$patch({ appointments, calls, locations, devices, zips })

      } catch (err) {
        if (mine !== sequence) return
        this.error = err.message
      } finally {
        if (mine === sequence) this.loading = false
      }
    },
    setPreset(key) {
      const range = presetRange(key, this.today, this.fiscalStartMonth)
      this.from = range.from
      this.to = range.to
      this.preset = key
      this.rangeError = ''
      return this.loadReports()
    },
    setCustom(from, to) {
      const problem = rangeProblem(from, to)
      if (problem) {
        this.rangeError = problem
        return Promise.resolve()
      }
      this.rangeError = ''
      this.from = from
      this.to = to
      this.preset = matchPreset(from, to, presetOptions(this.today, this.fiscalStartMonth))
      return this.loadReports()
    },
    setInterval(interval) {
      this.interval = interval
      return this.loadReports()
    },
    setMode(mode) {
      this.mode = mode
    },
  },
})