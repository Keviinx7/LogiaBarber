// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BookingFlow } from '../components/BookingFlow'
import type { AvailabilitySlot, Service } from '../api/types'

const catalog: Service[] = [7, 23].map((id) => ({ id, name: `Servicio ${id}`, description: 'Descripción API', price: '15.00', duration_minutes: 30, is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }))
const start = '2026-10-05T10:30:00.123456-05:00'
const slot = (starts_at = start, available = true): AvailabilitySlot => ({ starts_at, ends_at: new Date(Date.parse(starts_at) + 30 * 60_000).toISOString(), available })
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const fetchMock = vi.fn<typeof fetch>()
type Pending = { url: URL; signal?: AbortSignal | null; resolve: (response: Response) => void; reject: (error: Error) => void }
let pending: Pending[]
let defer: boolean
let initialSlots: AvailabilitySlot[]

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-05T14:00:00Z')) // 09:00 at the business
  pending = []; defer = false; initialSlots = [slot()]
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockImplementation(async (input, options) => {
    const url = new URL(String(input))
    if (url.pathname === '/api/business-config') return json({ timezone: 'America/Guayaquil' })
    if (url.pathname === '/api/barbers') return json([{ id: 11, name: 'Barbero 11' }, { id: 29, name: 'Barbero 29' }])
    if (url.pathname === '/api/availability') {
      if (defer) return new Promise<Response>((resolve, reject) => pending.push({ url, signal: options?.signal, resolve, reject }))
      return response(initialSlots, url)
    }
    if (url.pathname === '/api/appointments') return json({ ...JSON.parse(String(options?.body)), id: 99, status: 'pending', ends_at: slot().ends_at }, 201)
    throw new Error(`Unexpected ${url.pathname}`)
  })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

function response(slots: AvailabilitySlot[], url: URL) {
  return json({ date: url.searchParams.get('date'), service_id: Number(url.searchParams.get('service_id')), barber_id: Number(url.searchParams.get('barber_id')), slots })
}
const next = () => screen.getByRole<HTMLButtonElement>('button', { name: 'Continuar' })
const back = () => fireEvent.click(screen.getByRole('button', { name: /Atrás/ }))
const posts = () => fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')
async function openSlots() {
  const view = render(<BookingFlow services={catalog} initialService={7} onClose={() => {}} />)
  await waitFor(() => expect(next().disabled).toBe(false))
  fireEvent.click(next()); fireEvent.click(next())
  return view
}
async function choose() {
  await openSlots()
  fireEvent.click(await screen.findByRole('button', { name: '10:30' }))
}
function fill() {
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Cliente' } })
  fireEvent.change(screen.getByLabelText('Teléfono'), { target: { value: '099' } })
}
async function resolve(request: Pending, slots = [slot()]) {
  await act(async () => { request.resolve(response(slots, request.url)) })
}
function changeDate() {
  back()
  fireEvent.change(screen.getByLabelText('Fecha de la cita'), { target: { value: '2026-10-06' } })
  fireEvent.click(next())
}

describe(`P1.3 availability in ${Intl.DateTimeFormat().resolvedOptions().timeZone}`, () => {
  it('renders true slots and completely hides false slots', async () => {
    initialSlots = [slot(), slot('2026-10-05T16:30:00Z', false)]
    await openSlots()
    expect(await screen.findByRole('button', { name: '10:30' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '11:30' })).toBeNull()
  })

  it('shows an empty state when all slots are unavailable', async () => {
    initialSlots = [slot(start, false)]
    await openSlots()
    expect(await screen.findByText('No hay horarios disponibles para este día.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '10:30' })).toBeNull()
    expect(next().disabled).toBe(true)
  })

  it.each(['service', 'barber', 'date'])('changing %s invalidates results and selection', async (field) => {
    await choose()
    expect(next().disabled).toBe(false)
    defer = true
    back()
    if (field !== 'date') back()
    if (field === 'service') {
      back()
      fireEvent.click(screen.getByRole('button', { name: /Servicio 23/ }))
      fireEvent.click(next())
    }
    if (field === 'barber') fireEvent.click(screen.getByRole('button', { name: /Barbero 29/ }))
    if (field !== 'date') fireEvent.click(next())
    if (field === 'date') fireEvent.change(screen.getByLabelText('Fecha de la cita'), { target: { value: '2026-10-06' } })
    fireEvent.click(next())
    await waitFor(() => expect(pending).toHaveLength(1))
    expect(screen.queryByRole('button', { name: '10:30' })).toBeNull()
    expect(screen.getByRole<HTMLButtonElement>('button', { name: /Cargando/ }).disabled).toBe(true)
    const params = pending[0].url.searchParams
    expect(params.get('service_id')).toBe(field === 'service' ? '23' : '7')
    expect(params.get('barber_id')).toBe(field === 'barber' ? '29' : '11')
    expect(params.get('date')).toBe(field === 'date' ? '2026-10-06' : '2026-10-05')
    await resolve(pending[0])
    expect(screen.getByRole('button', { name: '10:30' }).classList.contains('selected')).toBe(false)
    expect(next().disabled).toBe(true)
    expect(posts()).toHaveLength(0)
  })

  it.each(['resolve', 'reject'])('late old response (%s) cannot replace new results or selection', async (completion) => {
    defer = true
    await openSlots()
    await waitFor(() => expect(pending).toHaveLength(1))
    const old = pending[0]
    expect(old.signal).toBeInstanceOf(AbortSignal)
    changeDate()
    await waitFor(() => expect(pending).toHaveLength(2))
    expect(old.signal?.aborted).toBe(true)
    await resolve(pending[1], [slot('2026-10-06T16:30:00Z')])
    fireEvent.click(screen.getByRole('button', { name: '11:30' }))
    await act(async () => {
      if (completion === 'resolve') old.resolve(response([slot()], old.url))
      else old.reject(new Error('Late failure'))
    })
    expect(screen.queryByRole('button', { name: '10:30' })).toBeNull()
    expect(screen.getByRole('button', { name: '11:30' }).classList.contains('selected')).toBe(true)
    expect(next().disabled).toBe(false)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('ignores AbortError without showing a failure', async () => {
    defer = true
    await openSlots()
    await waitFor(() => expect(pending).toHaveLength(1))
    await act(async () => { pending[0].reject(new DOMException('Cancelled', 'AbortError')) })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(next().disabled).toBe(true)
  })

  it('aborts on unmount', async () => {
    defer = true
    const view = await openSlots()
    await waitFor(() => expect(pending).toHaveLength(1))
    view.unmount()
    expect(pending[0].signal?.aborted).toBe(true)
  })

  it('a new error clears old slots/selection and is cleared when the query changes', async () => {
    await choose()
    defer = true
    changeDate()
    await waitFor(() => expect(pending).toHaveLength(1))
    await act(async () => { pending[0].resolve(json({ detail: 'Unavailable' }, 503)) })
    expect(screen.getByRole('alert').textContent).toBe('No se pudo cargar la disponibilidad.')
    expect(screen.queryByRole('button', { name: '10:30' })).toBeNull()
    expect(screen.queryByText('No hay horarios disponibles para este día.')).toBeNull()
    expect(next().disabled).toBe(true)
    back()
    fireEvent.change(screen.getByLabelText('Fecha de la cita'), { target: { value: '2026-10-07' } })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(posts()).toHaveLength(0)
  })

  it.each(['2026-10-05T15:30:00.123Z', '2026-10-05T15:31:00Z'])('does not POST when selection has expired at %s', async (now) => {
    await choose()
    fireEvent.click(next())
    fill()
    defer = true
    vi.setSystemTime(new Date(now))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar cita' }))
    expect(posts()).toHaveLength(0)
    expect(screen.getByRole('heading', { name: 'Escoge una hora' })).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('ya venció')
    await waitFor(() => expect(pending).toHaveLength(1))
    await resolve(pending[0], [slot('2026-10-05T16:30:00Z')])
    expect(next().disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: '11:30' }))
    fireEvent.click(next())
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar cita' }))
    await screen.findByRole('heading', { name: 'Cita reservada.' })
    expect(JSON.parse(String(posts()[0][1]?.body)).starts_at).toBe('2026-10-05T16:30:00Z')
  })

  it('keeps full timestamp, numeric API IDs and business time through summary and POST', async () => {
    await choose()
    fireEvent.click(next())
    expect(screen.getByText('10:30')).toBeTruthy()
    fill()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar cita' }))
    await screen.findByRole('heading', { name: 'Cita reservada.' })
    expect(posts()).toHaveLength(1)
    expect(JSON.parse(String(posts()[0][1]?.body))).toMatchObject({ starts_at: start, service_id: 7, barber_id: 11 })
    expect(screen.getByText('10:30')).toBeTruthy()
  })
})
