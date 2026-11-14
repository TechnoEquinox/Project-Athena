import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setCsrf } from './api'
import {
  downloadReport, getAppointmentsReport, getCallsReport, getCounters, getDevicesReport,
  getLocationsReport, reportUrl, getZipsReport,
} from './statsApi'
import { saveFile } from './lib/download'

vi.mock('./lib/download', () => ({ saveFile: vi.fn() }))

function reply(status, body) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    blob: () => Promise.resolve('BLOB'),
    headers: { get: () => 'attachment; filename="athena-zips-2026-01-01-to-2026-12-31.csv"' },
  })
}

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn()
  globalThis.fetch = fetchMock
  setCsrf('tok')
  saveFile.mockClear()
})

const url = () => fetchMock.mock.calls[0][0]
const RANGE = { from: '2026-01-01', to: '2026-12-31' }

describe('stats API', () => {
  it('loads the counters', async () => {
    fetchMock.mockReturnValue(reply(200, { today: '2026-11-12' }))
    expect(await getCounters()).toEqual({ today: '2026-11-12' })
    expect(url()).toBe('/api/stats/counters')
  })

  it.each([
    ['appointments', getAppointmentsReport],
    ['calls', getCallsReport],
    ['locations', getLocationsReport],
  ])('loads the %s report with a grouping', async (name, fn) => {
    fetchMock.mockReturnValue(reply(200, {}))
    await fn({ ...RANGE, interval: 'quarter' })
    expect(url()).toBe(`/api/stats/${name}?from=2026-01-01&to=2026-12-31&interval=quarter`)
  })

  it('loads the device report without a grouping', async () => {
    fetchMock.mockReturnValue(reply(200, {}))
    await getDevicesReport({ ...RANGE, interval: 'quarter' })
    expect(url()).toBe('/api/stats/devices?from=2026-01-01&to=2026-12-31')
  })

  it('loads the zip report without a grouping', async () => {
    fetchMock.mockReturnValue(reply(200, {}))
    await getZipsReport({ ...RANGE, interval: 'quarter' })
    expect(url()).toBe('/api/stats/zips?from=2026-01-01&to=2026-12-31')
  })

  it('builds the export address', () => {
    expect(reportUrl('zips', { ...RANGE, interval: 'month' })).toBe(
      '/api/stats/export?report=zips&from=2026-01-01&to=2026-12-31&interval=month',
    )
  })

  it('downloads a report and saves it under the name the server gave', async () => {
    fetchMock.mockReturnValue(reply(200, null))
    await downloadReport('zips', { ...RANGE, interval: 'month' })
    expect(url()).toBe('/api/stats/export?report=zips&from=2026-01-01&to=2026-12-31&interval=month')
    expect(saveFile).toHaveBeenCalledWith('BLOB', 'athena-zips-2026-01-01-to-2026-12-31.csv')
  })

  it('does not save anything when the download fails', async () => {
    fetchMock.mockReturnValue(reply(400, { error: 'bad_request', field: 'range' }))
    await expect(downloadReport('zips', RANGE)).rejects.toMatchObject({ status: 400 })
    expect(saveFile).not.toHaveBeenCalled()
  })
})