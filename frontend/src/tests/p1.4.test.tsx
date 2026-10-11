// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, within } from '@testing-library/react'
import { HomePage } from '../pages/HomePage'
import type { BusinessConfig } from '../api/types'

const config: BusinessConfig = {
  timezone: 'America/Guayaquil', opening_time: '10:00', closing_time: '21:00',
  lunch_start: '14:00', lunch_end: '15:00', working_days: [0, 1, 2, 3, 4, 5, 6],
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const fetchMock = vi.fn<typeof fetch>()
let publicConfig: unknown
const schedule = () => within(screen.getByRole('region', { name: 'Horario de atención' }))

beforeEach(() => {
  publicConfig = config
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockImplementation(async (input) => {
    const path = new URL(String(input)).pathname
    if (path === '/api/business-config') return json(publicConfig)
    if (path === '/api/services') return json([])
    throw new Error(`Unexpected request: ${path}`)
  })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('P1.4 public schedule', () => {
  it('shows the official hours, all seven days and non-bookable lunch from backend', async () => {
    render(<HomePage />)
    expect(await schedule().findByText('10:00–21:00')).toBeTruthy()
    expect(schedule().getByText('Lunes a domingo')).toBeTruthy()
    expect(schedule().getByText('14:00–15:00')).toBeTruthy()
    expect(schedule().getByText('Almuerzo · sin reservas')).toBeTruthy()
    expect(schedule().queryByText(/Cerrado/i)).toBeNull()
    expect(document.body.textContent).not.toMatch(/09:00|18:00|19:00/)
  })

  it('renders changed contract values instead of frontend business constants', async () => {
    publicConfig = { ...config, opening_time: '11:00', closing_time: '20:00', lunch_start: '13:00', lunch_end: '13:45', working_days: [1, 3, 6] }
    render(<HomePage />)
    expect(await schedule().findByText('11:00–20:00')).toBeTruthy()
    expect(schedule().getByText('13:00–13:45')).toBeTruthy()
    expect(schedule().getByText('Martes, Jueves, Domingo')).toBeTruthy()
    expect(schedule().queryByText('10:00–21:00')).toBeNull()
  })

  it('waits for the public contract without inventing hours', async () => {
    let resolve!: (value: Response) => void
    fetchMock.mockImplementation(async (input) => String(input).endsWith('/api/services')
      ? json([]) : new Promise<Response>((done) => { resolve = done }))
    render(<HomePage />)
    expect(schedule().getByText('Cargando horario de atención...')).toBeTruthy()
    expect(schedule().queryByText(/10:00|14:00/)).toBeNull()
    await act(async () => { resolve(json(config)) })
    expect(schedule().getByText('10:00–21:00')).toBeTruthy()
  })

  it.each(['HTTP', 'missing hours', 'invalid days'])('shows unavailable hours on %s without static fallback', async (failure) => {
    if (failure === 'HTTP') fetchMock.mockImplementation(async (input) => String(input).endsWith('/api/services') ? json([]) : json({}, 503))
    else publicConfig = failure === 'missing hours' ? { timezone: config.timezone } : { ...config, working_days: [7] }
    render(<HomePage />)
    expect(await schedule().findByText('No se pudo cargar el horario de atención.')).toBeTruthy()
    expect(schedule().queryByText(/10:00|14:00|Cerrado/)).toBeNull()
  })
})
