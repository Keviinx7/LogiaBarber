// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BookingFlow } from '../components/BookingFlow'
import { getBusinessConfig } from '../api/client'
import type { AvailabilitySlot, Service } from '../api/types'
import { businessDate, businessTime, displayCalendarDate } from '../utils/businessTime'

const timezone = 'America/Guayaquil'
const catalog: Service[] = [{ id: 7, name: 'Servicio API', description: 'Descripción API', price: '12.50', duration_minutes: 30, is_active: true, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }]
const start = '2026-10-05T10:30:00-05:00'
let slots: AvailabilitySlot[]
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
  vi.setSystemTime(new Date('2026-10-05T12:00:00Z'))
  slots = [{ starts_at: start, ends_at: '2026-10-05T11:00:00-05:00', available: true }]
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockImplementation(async (input, options) => {
    const url = new URL(String(input))
    if (url.pathname === '/api/business-config') return json({ timezone })
    if (url.pathname === '/api/barbers') return json([{ id: 11, name: 'Barbero API' }])
    if (url.pathname === '/api/availability') return json({ date: url.searchParams.get('date'), service_id: 7, barber_id: 11, slots })
    if (url.pathname === '/api/appointments' && options?.method === 'POST') {
      // The response may use UTC: presentation must still use the business zone.
      return json({ ...JSON.parse(String(options.body)), id: 99, starts_at: '2026-10-05T15:30:00Z', ends_at: '2026-10-05T16:00:00Z', status: 'pending' }, 201)
    }
    throw new Error(`Unexpected request: ${url.pathname}`)
  })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

const continueButton = () => screen.getByRole<HTMLButtonElement>('button', { name: 'Continuar' })
const dateInput = () => screen.getByLabelText<HTMLInputElement>('Fecha de la cita')
async function openDate() {
  render(<BookingFlow services={catalog} initialService={7} onClose={() => {}} />)
  await waitFor(() => expect(continueButton().disabled).toBe(false))
  fireEvent.click(continueButton())
}
async function openSummary(hour = '10:30') {
  await openDate()
  fireEvent.click(continueButton())
  fireEvent.click(await screen.findByRole('button', { name: hour }))
  fireEvent.click(continueButton())
}
function fillCustomer() {
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Cliente P1.2' } })
  fireEvent.change(screen.getByLabelText('Teléfono'), { target: { value: '0990000000' } })
}

describe(`P1.2 device timezone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`, () => {
  it.each([
    ['18:59', '2026-10-05T23:59:00Z', '2026-10-05'],
    ['19:00', '2026-10-06T00:00:00Z', '2026-10-05'],
    ['23:59', '2026-10-06T04:59:00Z', '2026-10-05'],
    ['00:00', '2026-10-06T05:00:00Z', '2026-10-06'],
  ])('Guayaquil %s: utility, initial date and min agree', async (_hour, instant, day) => {
    vi.setSystemTime(new Date(instant))
    expect(businessDate(new Date(), timezone)).toBe(day)
    await openDate()
    expect(dateInput().value).toBe(day)
    expect(dateInput().min).toBe(day)
  })

  it('formats calendar dates without applying the device timezone', () => {
    expect(displayCalendarDate('2026-10-05')).toBe('lunes, 5 de octubre')
    expect(businessTime(start, timezone)).toBe('10:30')
    expect(businessTime('2026-10-05T15:30:00Z', timezone)).toBe('10:30')
  })

  it('uses the backend timezone even when it changes to another IANA zone', async () => {
    vi.setSystemTime(new Date('2026-10-05T23:30:00Z'))
    fetchMock.mockImplementationOnce(async () => json([{ id: 11, name: 'Barbero API' }]))
    fetchMock.mockImplementationOnce(async () => json({ timezone: 'Asia/Tokyo' }))
    await openDate()
    expect(dateInput().min).toBe('2026-10-06')
    fireEvent.click(continueButton())
    expect(await screen.findByRole('button', { name: '00:30' })).toBeTruthy()
  })

  it.each([start, '2026-10-05T15:30:00Z', '2026-10-05T17:30:00+02:00', '2026-10-05T10:30:00.123456-05:00'])('preserves the exact timestamp %s for POST and formats summary/confirmation', async (timestamp) => {
    slots[0].starts_at = timestamp
    await openSummary()
    expect(screen.getByText('10:30')).toBeTruthy()
    expect(screen.getByText('lunes, 5 de octubre')).toBeTruthy()
    fillCustomer()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar cita' }))
    await screen.findByRole('heading', { name: 'Cita reservada.' })
    const posts = fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(JSON.parse(String(posts[0][1]?.body)).starts_at).toBe(timestamp)
    expect(screen.getByText('10:30')).toBeTruthy()
    expect(screen.getByText('lunes, 5 de octubre')).toBeTruthy()
  })

  it('distinguishes slots with the same visible HH:mm and hides occupied slots under P1.3', async () => {
    slots.push({ ...slots[0], starts_at: '2026-10-05T10:30:30-05:00' })
    slots.push({ ...slots[0], starts_at: '2026-10-05T11:30:00-05:00', available: false })
    await openDate()
    fireEvent.click(continueButton())
    const buttons = await screen.findAllByRole('button', { name: '10:30' })
    expect(screen.queryByRole('button', { name: '11:30' })).toBeNull()
    fireEvent.click(buttons[1])
    expect(buttons[0].classList.contains('selected')).toBe(false)
    expect(buttons[1].classList.contains('selected')).toBe(true)
    fireEvent.click(continueButton())
    fillCustomer()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar cita' }))
    await screen.findByRole('heading', { name: 'Cita reservada.' })
    const post = fetchMock.mock.calls.find(([, options]) => options?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body)).starts_at).toBe(slots[1].starts_at)
  })

  it.each(['focus', 'visibility', 'interval'])('refreshes min and date across midnight via %s', async (trigger) => {
    vi.setSystemTime(new Date('2026-10-06T04:59:59Z'))
    await openDate()
    expect(dateInput().min).toBe('2026-10-05')
    await act(async () => {
      if (trigger === 'interval') vi.advanceTimersByTime(30_000)
      else {
        vi.setSystemTime(new Date('2026-10-06T05:00:00Z'))
        if (trigger === 'focus') window.dispatchEvent(new Event('focus'))
        else document.dispatchEvent(new Event('visibilitychange'))
      }
    })
    expect(dateInput().min).toBe('2026-10-06')
    expect(dateInput().value).toBe('2026-10-06')
  })

  it('preserves a future chosen calendar date while updating min', async () => {
    await openDate()
    fireEvent.change(dateInput(), { target: { value: '2026-10-12' } })
    vi.setSystemTime(new Date('2026-10-06T05:00:00Z'))
    fireEvent(window, new Event('focus'))
    expect(dateInput().min).toBe('2026-10-06')
    expect(dateInput().value).toBe('2026-10-12')
  })

  it.each(['focus', 'submit'])('invalidates yesterday’s slot on %s without submitting it', async (trigger) => {
    await openSummary()
    fillCustomer()
    vi.setSystemTime(new Date('2026-10-06T05:00:00Z'))
    if (trigger === 'focus') fireEvent(window, new Event('focus'))
    else fireEvent.click(screen.getByRole('button', { name: 'Confirmar cita' }))
    expect(dateInput().value).toBe('2026-10-06')
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
    fireEvent.click(continueButton())
    await screen.findByRole('button', { name: '10:30' })
    expect(continueButton().disabled).toBe(true)
  })

  it.each([{ timezone: 'Invalid/Zone' }, {}, { timezone: '' }, null])('rejects invalid public configuration %j explicitly', async (config) => {
    fetchMock.mockResolvedValueOnce(json(config))
    await expect(getBusinessConfig()).rejects.toThrow()
  })

  it('blocks booking on configuration failure without a fallback zone', async () => {
    fetchMock.mockImplementation(async (input) => String(input).endsWith('/api/barbers')
      ? json([{ id: 11, name: 'Barbero API' }]) : json({ timezone: 'Invalid/Zone' }))
    render(<BookingFlow services={catalog} initialService={7} onClose={() => {}} />)
    expect((await screen.findByRole('alert')).textContent).toContain('zona horaria válida')
    expect(continueButton().disabled).toBe(true)
    expect(screen.queryByLabelText('Fecha de la cita')).toBeNull()
    expect(fetchMock.mock.calls.some(([url]) => /availability|appointments/.test(String(url)))).toBe(false)
  })
})
