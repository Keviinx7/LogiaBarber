// @vitest-environment jsdom
/**
 * Integration boundary: actual HomePage -> BookingFlow -> API client, in jsdom.
 * HTTP and persistence are simulated here; this does NOT attest PostgreSQL,
 * FastAPI validation, browser rendering, or the exclusion constraint.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HomePage } from '../pages/HomePage'
import type { AvailabilitySlot, BusinessConfig, Service } from '../api/types'

const catalog: Service[] = [
  { id: 47, name: 'Corte catálogo API', description: 'Descripción del servidor', duration_minutes: 30, price: '15.00', is_active: true, created_at: '', updated_at: '' },
  { id: 89, name: 'Servicio largo API', description: null, duration_minutes: 45, price: '22.50', is_active: true, created_at: '', updated_at: '' },
]
const barbers = [{ id: 31, name: 'Barbero treinta y uno' }, { id: 73, name: 'Barbero setenta y tres' }]
const config: BusinessConfig = { timezone: 'America/Guayaquil', opening_time: '10:00', closing_time: '21:00', lunch_start: '14:00', lunch_end: '15:00', working_days: [0, 1, 2, 3, 4, 5, 6] }
const testDate = '2031-04-20'
const fullStart = `${testDate}T10:30:00.123456-05:00`
type Posted = { client_name: string; client_phone: string; service_id: number; barber_id: number; starts_at: string; notes?: string }
type Captured = { url: URL; signal?: AbortSignal | null; resolve: (response: Response) => void }
const fetchMock = vi.fn<typeof fetch>()
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
let failures: Set<string>
let saved: Posted[]
let pending: Captured[]
let deferAvailability: boolean
let conflictOnce: boolean
let postMode: 'success' | 'network' | 'pending'
let resolvePost: (response: Response) => void

function makeSlots(date: string, serviceId: number, barberId: number): AvailabilitySlot[] {
  const duration = catalog.find((service) => service.id === serviceId)!.duration_minutes
  return ['10:30', '11:30'].map((time) => {
    const starts_at = `${date}T${time}:00.123456-05:00`
    return { starts_at, ends_at: new Date(Date.parse(starts_at) + duration * 60_000).toISOString(), available: Date.parse(starts_at) > Date.now() && !saved.some((appointment) => appointment.barber_id === barberId && appointment.starts_at === starts_at) }
  })
}
function availabilityResponse(url: URL) {
  const date = url.searchParams.get('date')!
  const service_id = Number(url.searchParams.get('service_id'))
  const barber_id = Number(url.searchParams.get('barber_id'))
  return json({ date, service_id, barber_id, slots: makeSlots(date, service_id, barber_id) })
}
function successfulPost(body: Posted) {
  saved.push(body)
  return json({ ...body, id: saved.length + 400, ends_at: new Date(Date.parse(body.starts_at) + catalog.find((service) => service.id === body.service_id)!.duration_minutes * 60_000).toISOString(), status: 'pending' }, 201)
}
const postCalls = () => fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')
const availabilityCalls = () => fetchMock.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/api/availability')
const flow = () => within(screen.getByRole('region', { name: 'Flujo de reserva' }))
const next = () => flow().getByRole<HTMLButtonElement>('button', { name: 'Continuar' })
const back = async () => userEvent.click(flow().getByRole('button', { name: 'Atrás' }))
const confirm = () => flow().getByRole<HTMLButtonElement>('button', { name: 'Confirmar cita' })

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(`${testDate}T14:00:00Z`))
  failures = new Set(); saved = []; pending = []; deferAvailability = false; conflictOnce = false; postMode = 'success'
  fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockImplementation(async (input, options) => {
    const url = new URL(String(input))
    if (failures.has(url.pathname)) return json({ detail: 'Simulated unavailable resource' }, 503)
    if (url.pathname === '/api/services') return json(catalog)
    if (url.pathname === '/api/barbers') return json(barbers)
    if (url.pathname === '/api/business-config') return json(config)
    if (url.pathname === '/api/availability') {
      if (deferAvailability) return new Promise<Response>((resolve) => pending.push({ url, signal: options?.signal, resolve }))
      return availabilityResponse(url)
    }
    if (url.pathname === '/api/appointments' && options?.method === 'POST') {
      const body: Posted = JSON.parse(String(options.body))
      if (postMode === 'network') { saved.push(body); throw new TypeError('Simulated connection lost after commit') }
      if (postMode === 'pending') return new Promise<Response>((resolve) => { resolvePost = resolve })
      if (conflictOnce) { conflictOnce = false; saved.push(body); return json({ detail: 'Unavailable interval' }, 409) }
      return successfulPost(body)
    }
    throw new Error(`Unexpected test request ${url.pathname}`)
  })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

async function openHomeBooking() {
  render(<HomePage />)
  const title = await screen.findByRole('heading', { name: catalog[0].name })
  expect(screen.getByText('Descripción del servidor')).toBeTruthy()
  await userEvent.click(within(title.closest('article')!).getByRole('button', { name: 'Elegir servicio' }))
  await flow().findByRole('heading', { name: 'Elige tu barbero' })
}
async function openSlots() {
  await openHomeBooking()
  await waitFor(() => expect(next().disabled).toBe(false))
  await userEvent.click(flow().getByRole('button', { name: new RegExp(barbers[1].name) }))
  await userEvent.click(next())
  expect(flow().getByLabelText<HTMLInputElement>('Fecha de la cita').value).toBe(testDate)
  await userEvent.click(next())
}
async function openForm() {
  await openSlots()
  await userEvent.click(await flow().findByRole('button', { name: '10:30' }))
  await userEvent.click(next())
  await userEvent.type(flow().getByLabelText('Nombre'), '  Cliente integrado  ')
  await userEvent.type(flow().getByLabelText('Teléfono'), '  +34 600 123  ')
  await userEvent.type(flow().getByLabelText(/Notas/), 'Sin cambios de estilo')
}
async function success() {
  await screen.findByRole('heading', { name: 'Cita reservada.' })
  expect(screen.queryByRole('alert')).toBeNull()
}

describe(`P1.6 HomePage integration (simulated HTTP; ${Intl.DateTimeFormat().resolvedOptions().timeZone})`, () => {
  it('completes catalog -> API IDs -> barber -> business date -> full timestamp -> POST -> confirmation', async () => {
    await openForm()
    const booking = flow()
    expect(booking.getByText(catalog[0].name)).toBeTruthy()
    expect(booking.getByText(barbers[1].name)).toBeTruthy()
    expect(booking.getByText('10:30')).toBeTruthy()
    expect(screen.getByText('10:00–21:00')).toBeTruthy()
    expect(screen.getByText('14:00–15:00')).toBeTruthy()
    await userEvent.click(confirm()); await success()
    const query = new URL(String(availabilityCalls()[0][0])).searchParams
    expect(Object.fromEntries(query)).toEqual({ service_id: '47', barber_id: '73', date: testDate })
    expect(postCalls()).toHaveLength(1)
    expect(saved).toEqual([{ client_name: 'Cliente integrado', client_phone: '+34 600 123', service_id: 47, barber_id: 73, starts_at: fullStart, notes: 'Sin cambios de estilo' }])
    expect(screen.getByText('10:30')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: /Volver al inicio/ }))
    expect(screen.queryByRole('region', { name: 'Flujo de reserva' })).toBeNull()
  })

  it('recovers a catalog failure with explicit retry and completes the booking', async () => {
    failures.add('/api/services'); render(<HomePage />)
    expect((await screen.findByRole('alert')).textContent).toContain('catálogo')
    expect(screen.queryAllByRole('article')).toHaveLength(0)
    failures.clear(); await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    const title = await screen.findByRole('heading', { name: catalog[0].name })
    await userEvent.click(within(title.closest('article')!).getByRole('button', { name: 'Elegir servicio' }))
    await waitFor(() => expect(next().disabled).toBe(false))
    await userEvent.click(next()); await userEvent.click(next())
    await userEvent.click(await flow().findByRole('button', { name: '10:30' })); await userEvent.click(next())
    await userEvent.type(flow().getByLabelText('Nombre'), 'Cliente'); await userEvent.type(flow().getByLabelText('Teléfono'), '+1 123')
    await userEvent.click(confirm()); await success()
    expect(fetchMock.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/api/services')).toHaveLength(2)
    expect(saved[0].service_id).toBe(47)
  })

  it.each([
    { path: '/api/barbers', retry: 'Reintentar barberos' },
    { path: '/api/business-config', retry: 'Reintentar configuración' },
  ])('recovers $path while preserving the open reservation', async ({ path, retry }) => {
    failures.add(path); await openHomeBooking()
    expect((await flow().findByRole('alert')).textContent).toContain('No se pudo cargar')
    expect(next().disabled).toBe(true); expect(availabilityCalls()).toHaveLength(0)
    failures.clear(); await userEvent.click(flow().getByRole('button', { name: retry }))
    await waitFor(() => expect(next().disabled).toBe(false))
    expect(flow().queryByRole('alert')).toBeNull()
    await userEvent.click(next()); await userEvent.click(next())
    expect(await flow().findByRole('button', { name: '10:30' })).toBeTruthy()
    expect(new URL(String(availabilityCalls()[0][0])).searchParams.get('service_id')).toBe('47')
  })

  it('recovers failed availability without enabling confirmation or reusing stale data', async () => {
    failures.add('/api/availability'); await openSlots()
    expect((await flow().findByRole('alert')).textContent).toContain('disponibilidad')
    expect(next().disabled).toBe(true); expect(flow().queryByRole('button', { name: '10:30' })).toBeNull()
    expect(postCalls()).toHaveLength(0)
    failures.clear(); await userEvent.click(flow().getByRole('button', { name: 'Reintentar horarios' }))
    await userEvent.click(await flow().findByRole('button', { name: '10:30' }))
    expect(next().disabled).toBe(false); expect(availabilityCalls()).toHaveLength(2)
  })

  it('recovers a 409 via refreshed availability, preserves details, and submits the newly selected timestamp', async () => {
    conflictOnce = true; await openForm(); await userEvent.click(confirm())
    await flow().findByRole('heading', { name: 'Escoge una hora' })
    expect(flow().getByRole('alert').textContent).toContain('no está disponible')
    const alternative = await flow().findByRole('button', { name: '11:30' })
    expect(flow().queryByRole('button', { name: '10:30' })).toBeNull()
    expect(next().disabled).toBe(true)
    await userEvent.click(alternative); await userEvent.click(next())
    expect(flow().getByLabelText<HTMLInputElement>('Nombre').value).toBe('  Cliente integrado  ')
    expect(flow().getByLabelText<HTMLInputElement>('Teléfono').value).toBe('  +34 600 123  ')
    await userEvent.click(confirm()); await success()
    expect(postCalls()).toHaveLength(2)
    expect(JSON.parse(String(postCalls()[1][1]?.body)).starts_at).toBe(`${testDate}T11:30:00.123456-05:00`)
  })

  it('does not retry POST after a simulated connection loss following persistence', async () => {
    postMode = 'network'; await openForm(); await userEvent.click(confirm())
    const alert = await flow().findByRole('alert')
    expect(alert.textContent).toContain('podría haberse registrado')
    expect(alert.textContent).not.toMatch(/no se creó|object Object/)
    await act(async () => { await Promise.resolve() })
    expect(postCalls()).toHaveLength(1); expect(saved).toHaveLength(1)
    expect(flow().getByLabelText<HTMLInputElement>('Nombre').value).toBe('  Cliente integrado  ')
  })

  it('blocks a synchronous double submit and navigation while the POST is pending', async () => {
    postMode = 'pending'; await openForm(); const button = confirm()
    act(() => { button.click(); button.click() })
    expect(postCalls()).toHaveLength(1)
    expect(flow().getByRole<HTMLButtonElement>('button', { name: 'Atrás' }).disabled).toBe(true)
    expect(flow().getByRole<HTMLButtonElement>('button', { name: 'Cerrar reserva' }).disabled).toBe(true)
    expect(flow().getByLabelText<HTMLInputElement>('Nombre').disabled).toBe(true)
    const body: Posted = JSON.parse(String(postCalls()[0][1]?.body))
    await act(async () => { resolvePost(successfulPost(body)) }); await success()
    expect(saved).toHaveLength(1)
  })

  it('rejects an expired selection before POST and obtains another future slot', async () => {
    await openForm(); vi.setSystemTime(new Date(`${testDate}T15:30:01Z`)); await userEvent.click(confirm())
    await flow().findByRole('heading', { name: 'Escoge una hora' })
    expect(flow().getByRole('alert').textContent).toContain('ya venció')
    expect(postCalls()).toHaveLength(0)
    await userEvent.click(await flow().findByRole('button', { name: '11:30' })); await userEvent.click(next())
    await userEvent.click(confirm()); await success()
    expect(saved[0].starts_at).toBe(`${testDate}T11:30:00.123456-05:00`)
  })

  it.each(['service', 'barber', 'date'])('changing %s invalidates old results and selection across the integrated flow', async (field) => {
    await openSlots(); await userEvent.click(await flow().findByRole('button', { name: '10:30' }))
    expect(next().disabled).toBe(false); deferAvailability = true
    await back()
    if (field !== 'date') await back()
    if (field === 'service') {
      await back(); await userEvent.click(flow().getByRole('button', { name: new RegExp(catalog[1].name) })); await userEvent.click(next())
    }
    if (field === 'barber') await userEvent.click(flow().getByRole('button', { name: new RegExp(barbers[0].name) }))
    if (field !== 'date') await userEvent.click(next())
    if (field === 'date') fireEvent.change(flow().getByLabelText('Fecha de la cita'), { target: { value: '2031-04-21' } })
    await userEvent.click(next()); await waitFor(() => expect(pending).toHaveLength(1))
    expect(flow().queryByRole('button', { name: '10:30' })).toBeNull()
    expect(flow().getByRole<HTMLButtonElement>('button', { name: /Cargando/ }).disabled).toBe(true)
    const query = pending[0].url.searchParams
    expect(Object.fromEntries(query)).toEqual({ service_id: field === 'service' ? '89' : '47', barber_id: field === 'barber' ? '31' : '73', date: field === 'date' ? '2031-04-21' : testDate })
    await act(async () => pending[0].resolve(availabilityResponse(pending[0].url)))
    expect(flow().getByRole('button', { name: '10:30' }).classList.contains('selected')).toBe(false)
    expect(next().disabled).toBe(true); expect(postCalls()).toHaveLength(0)
  })
})
