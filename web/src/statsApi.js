import { api, download, qs } from './api'
import { saveFile } from './lib/download'

export const getCounters = () => api.get('/api/stats/counters')

export const getAppointmentsReport = ({ from, to, interval }) =>
  api.get(`/api/stats/appointments${qs({ from, to, interval })}`)

export const getCallsReport = ({ from, to, interval }) =>
  api.get(`/api/stats/calls${qs({ from, to, interval })}`)

export const getLocationsReport = ({ from, to, interval }) =>
  api.get(`/api/stats/locations${qs({ from, to, interval })}`)

export const getDevicesReport = ({ from, to }) => api.get(`/api/stats/devices${qs({ from, to })}`)

export const reportUrl = (report, { from, to, interval }) =>
  `/api/stats/export${qs({ report, from, to, interval })}`

export async function downloadReport(report, params) {
  const { blob, filename } = await download(reportUrl(report, params))
  saveFile(blob, filename ?? `athena-${report}.csv`)
}

export const getZipsReport = ({ from, to }) => api.get(`/api/stats/zips${qs({ from, to })}`)