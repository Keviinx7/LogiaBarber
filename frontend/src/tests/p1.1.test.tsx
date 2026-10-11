// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createAppointment, getAvailability, getServices } from '../api/client'
import type { Service } from '../api/types'
import { ServiceCard } from '../components/ServiceCard'
import { BookingFlow } from '../components/BookingFlow'
import { HomePage } from '../pages/HomePage'

const catalog: Service[] = [
  { id: 2, name: 'Corte de autor', description: 'Descripción desde API', price: '12.50', duration_minutes: 35, is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 7, name: 'Ritual completo', description: null, price: '23.75', duration_minutes: 65, is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 15, name: 'Perfilado especial', description: 'Otro servicio real', price: '8.00', duration_minutes: 25, is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
]
const inactive: Service = { ...catalog[0], id: 40, name: 'Servicio retirado', is_active: false }
const prices = ['12,50', '23,75', '8,00']
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const fetchMock = vi.fn<typeof fetch>()

function mockHttp(services: Service[] = catalog) {
  fetchMock.mockImplementation(async (input, options) => {
    const url = new URL(String(input))
    if (url.pathname === '/api/business-config') return json({ timezone: 'America/Guayaquil', opening_time: '10:00', closing_time: '21:00', lunch_start: '14:00', lunch_end: '15:00', working_days: [0, 1, 2, 3, 4, 5, 6] })
    if (url.pathname === '/api/services') return json(services)
    if (url.pathname === '/api/barbers') return json([{ id: 11, name: 'Barbero API' }])
    if (url.pathname === '/api/availability') return json({ slots: [{ starts_at: '2026-10-12T10:00:00-05:00', ends_at: '2026-10-12T11:05:00-05:00', available: true }] })
    if (url.pathname === '/api/appointments' && options?.method === 'POST') return json({ ...JSON.parse(String(options.body)), id: 99, status: 'pending', ends_at: '2026-10-12T11:05:00-05:00' }, 201)
    throw new Error(`Unexpected request: ${url.pathname}`)
  })
}

beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); mockHttp() })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const continueButton = () => screen.getByRole<HTMLButtonElement>('button', { name: 'Continuar' })
async function readyToContinue() { await waitFor(() => expect(continueButton().disabled).toBe(false)) }

describe('P1.1 ServiceCard', () => {
  it.each(catalog.map((service, index) => ({ service, price: prices[index] })))('renders API data and passes numeric ID $service.id unchanged', async ({ service, price }) => {
    const original = structuredClone(service)
    const onBook = vi.fn()
    const { container } = render(<ServiceCard service={service} onBook={onBook} />)
    expect(screen.getByRole('heading', { name: service.name })).toBeTruthy()
    expect(screen.getByText(`${service.duration_minutes} min`)).toBeTruthy()
    expect(container.querySelector('strong')?.textContent).toContain(price)
    expect(container.querySelector('strong')?.textContent).toContain('$')
    if (service.description) expect(screen.getByText(service.description)).toBeTruthy()
    else expect(container.querySelector('p')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Elegir servicio' }))
    expect(onBook).toHaveBeenCalledExactlyOnceWith(service.id)
    expect(service).toEqual(original)
  })
})

describe('P1.1 HomePage and shared catalog', () => {
  it('shows loading until GET /api/services resolves', async () => {
    let resolve!: (response: Response) => void
    fetchMock.mockReturnValueOnce(new Promise<Response>((done) => { resolve = done }))
    render(<HomePage />)
    expect(screen.getByRole('status').textContent).toBe('Cargando servicios...')
    expect(screen.queryAllByRole('article')).toHaveLength(0)
    await act(async () => { resolve(json(catalog)) })
    expect(await screen.findAllByRole('article')).toHaveLength(3)
  })

  it('renders only active API services and shares the same catalog with BookingFlow', async () => {
    mockHttp([...catalog, inactive])
    render(<HomePage />)
    const cards = await screen.findAllByRole('article')
    expect(cards).toHaveLength(3)
    catalog.forEach((service, i) => expect(within(cards[i]).getByRole('heading', { name: service.name })).toBeTruthy())
    await userEvent.click(screen.getAllByRole('button', { name: /Reservar cita/ })[0])
    const flow = screen.getByRole('region', { name: 'Flujo de reserva' })
    for (const [index, service] of catalog.entries()) {
      const choice = within(flow).getByRole('button', { name: new RegExp(service.name) })
      expect(choice.textContent).toContain(`${service.duration_minutes} min`)
      expect(choice.textContent).toContain(prices[index])
    }
    expect(screen.queryByText(inactive.name)).toBeNull()
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/api/services'))).toHaveLength(1)
  })

  it.each([2, 7, 15])('preserves card ID %i through preselection, availability and POST', async (id) => {
    const user = userEvent.setup()
    render(<HomePage />)
    const title = await screen.findByRole('heading', { name: catalog.find((s) => s.id === id)!.name })
    await user.click(within(title.closest('article')!).getByRole('button', { name: 'Elegir servicio' }))
    expect(await screen.findByRole('heading', { name: 'Elige tu barbero' })).toBeTruthy()
    await readyToContinue()
    await user.click(continueButton())
    await user.click(continueButton())
    await user.click(await screen.findByRole('button', { name: '10:00' }))
    await user.click(continueButton())
    await user.type(screen.getByLabelText('Nombre'), 'Cliente de prueba')
    await user.type(screen.getByLabelText('Teléfono'), '0990000000')
    await user.click(screen.getByRole('button', { name: 'Confirmar cita' }))
    expect(await screen.findByRole('heading', { name: 'Cita reservada.' })).toBeTruthy()
    const availability = fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/availability?'))
    expect(availability).toHaveLength(1)
    expect(new URL(String(availability[0][0])).searchParams.get('service_id')).toBe(String(id))
    expect(new URL(String(availability[0][0])).searchParams.get('barber_id')).toBe('11')
    const posts = fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(posts).toHaveLength(1)
    const body = JSON.parse(String(posts[0][1]?.body))
    expect(body.service_id).toBe(id)
    expect(body.barber_id).toBe(11)
    expect(body.starts_at).toMatch(/T10:00:00-05:00$/)
    for (const [url, options] of fetchMock.mock.calls) {
      expect(`${url} ${options?.body ?? ''}`).not.toMatch(/classic|combo|beard|NaN|null/)
    }
  })

  it('handles an empty catalog in HomePage and BookingFlow', async () => {
    mockHttp([])
    render(<HomePage />)
    expect(await screen.findByText('No hay servicios disponibles.')).toBeTruthy()
    expect(screen.queryAllByRole('article')).toHaveLength(0)
    await userEvent.click(screen.getAllByRole('button', { name: /Reservar cita/ })[0])
    await screen.findByRole('button', { name: 'Continuar' })
    expect(continueButton().disabled).toBe(true)
    expect(screen.getAllByText('No hay servicios disponibles.')).toHaveLength(2)
    expect(fetchMock.mock.calls.some(([url]) => /availability|appointments/.test(String(url)))).toBe(false)
  })

  it.each(['HTTP', 'network'])('shows %s error without mock fallback and retries successfully', async (failure) => {
    if (failure === 'HTTP') fetchMock.mockResolvedValueOnce(json({ detail: 'Unavailable' }, 503))
    else fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    render(<HomePage />)
    expect((await screen.findByRole('alert')).textContent).toBe('No se pudo cargar el catálogo de servicios.')
    expect(screen.queryAllByRole('article')).toHaveLength(0)
    expect(screen.queryByText('No hay servicios disponibles.')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findAllByRole('article')).toHaveLength(3)
    expect(screen.queryByRole('alert')).toBeNull()
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/api/services'))).toHaveLength(2)
  })

  it('can retry the shared catalog from an open BookingFlow', async () => {
    fetchMock.mockResolvedValueOnce(json({}, 500))
    render(<HomePage />)
    await screen.findByRole('alert')
    await userEvent.click(screen.getAllByRole('button', { name: /Reservar cita/ })[0])
    const flow = within(screen.getByRole('region', { name: 'Flujo de reserva' }))
    expect(flow.getByRole('alert').textContent).toContain('No se pudo cargar')
    await userEvent.click(flow.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findAllByRole('article')).toHaveLength(3)
    expect(flow.getAllByRole('button', { pressed: false })).toHaveLength(3)
    expect(continueButton().disabled).toBe(true)
  })
})

describe('P1.1 BookingFlow preselection', () => {
  it.each([2, 7, 15])('accepts valid numeric preselection %i', async (id) => {
    render(<BookingFlow services={catalog} initialService={id} onClose={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Elige tu barbero' })).toBeTruthy()
    await readyToContinue()
    await userEvent.click(screen.getByRole('button', { name: 'Atrás' }))
    expect(screen.getByRole('button', { pressed: true }).textContent).toContain(catalog.find((s) => s.id === id)!.name)
  })

  it.each([999, 40])('rejects missing or inactive preselection %i and requires explicit selection', async (id) => {
    render(<BookingFlow services={[...catalog, inactive]} initialService={id} onClose={() => {}} />)
    await screen.findByRole('button', { name: 'Continuar' })
    expect(screen.getByRole('heading', { name: 'Elige tu servicio' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('Elige un servicio válido')
    expect(continueButton().disabled).toBe(true)
    expect(screen.queryByRole('button', { pressed: true })).toBeNull()
    expect(screen.queryByText(inactive.name)).toBeNull()
    expect(fetchMock.mock.calls.some(([url]) => /availability|appointments/.test(String(url)))).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: /Ritual completo/ }))
    expect(continueButton().disabled).toBe(false)
    await userEvent.click(continueButton())
    expect(screen.getByRole('heading', { name: 'Elige tu barbero' })).toBeTruthy()
  })

  it('clears a preselection when it disappears from the current catalog', async () => {
    const { rerender } = render(<BookingFlow services={catalog} initialService={7} onClose={() => {}} />)
    await readyToContinue()
    rerender(<BookingFlow services={catalog.filter((s) => s.id !== 7)} initialService={7} onClose={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Elige tu servicio' })).toBeTruthy()
    expect(continueButton().disabled).toBe(true)
    expect(screen.queryByRole('button', { pressed: true })).toBeNull()
  })
})

describe('P1.1 API ID guards', () => {
  const invalidIds = ['classic', 'combo', 'beard', '7', NaN, Infinity, null, undefined, 0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]
  it.each(invalidIds)('rejects invalid ID %s before any availability or reservation request', async (invalid) => {
    // Intentionally bypass TypeScript to check the runtime boundary too.
    const id = invalid as number
    await expect(getAvailability(id, 11, '2026-10-12')).rejects.toThrow('entero positivo')
    await expect(getAvailability(7, id, '2026-10-12')).rejects.toThrow('entero positivo')
    const payload = { client_name: 'Cliente', client_phone: '099', service_id: 7, barber_id: 11, starts_at: '2026-10-12T10:00:00-05:00' }
    await expect(createAppointment({ ...payload, service_id: id })).rejects.toThrow('entero positivo')
    await expect(createAppointment({ ...payload, barber_id: id })).rejects.toThrow('entero positivo')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects nonnumeric IDs in the service response instead of converting them', async () => {
    fetchMock.mockResolvedValueOnce(json([{ ...catalog[0], id: 'classic' }]))
    await expect(getServices()).rejects.toThrow('entero positivo')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
