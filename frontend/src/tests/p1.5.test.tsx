// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ApiError, createAppointment, getAvailability, validCalendarDate } from '../api/client'
import { BookingFlow } from '../components/BookingFlow'
import { HomePage } from '../pages/HomePage'
import type { Service } from '../api/types'

const service: Service = { id: 7, name: 'Servicio API', description: 'Real', price: '12.00', duration_minutes: 30, is_active: true, created_at: '', updated_at: '' }
const services = [service]
const config = { timezone: 'America/Guayaquil', opening_time: '10:00', closing_time: '21:00', lunch_start: '14:00', lunch_end: '15:00', working_days: [0, 1, 2, 3, 4, 5, 6] }
const start = '2026-10-05T10:30:00.123456-05:00'
const slot = { starts_at: start, ends_at: '2026-10-05T11:00:00-05:00', available: true }
const payload = { client_name: 'Cliente', client_phone: '+34 600 123', service_id: 7, barber_id: 11, starts_at: start }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const fetchMock = vi.fn<typeof fetch>()
let post: () => Promise<Response>
let overrides: Record<string, () => Promise<Response>>
const posts = () => fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')
const next = () => screen.getByRole<HTMLButtonElement>('button', { name: 'Continuar' })
const confirm = () => screen.getByRole<HTMLButtonElement>('button', { name: 'Confirmar cita' })
const onClose = vi.fn()
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-05T14:00:00Z'))
  overrides = {}; onClose.mockReset(); fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock)
  post = async () => json({ ...payload, ends_at: slot.ends_at, id: 80, status: 'pending' }, 201)
  fetchMock.mockImplementation(async (input, options) => {
    const url = new URL(String(input))
    if (overrides[url.pathname]) return overrides[url.pathname]()
    if (options?.method === 'POST') return post()
    if (url.pathname === '/api/services') return json(services)
    if (url.pathname === '/api/business-config') return json(config)
    if (url.pathname === '/api/barbers') return json([{ id: 11, name: 'Barbero API' }])
    if (url.pathname === '/api/availability') return json({ slots: [slot] })
    throw new Error('Unexpected request')
  })
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })
async function open() {
  const view = render(<BookingFlow services={services} initialService={7} onClose={onClose} />)
  await waitFor(() => expect(next().disabled).toBe(false)); return view
}
async function slots() { const view = await open(); fireEvent.click(next()); fireEvent.click(next()); return view }
async function form() {
  const view = await slots(); fireEvent.click(await screen.findByRole('button', { name: '10:30' })); fireEvent.click(next())
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Cliente' } })
  fireEvent.change(screen.getByLabelText('Teléfono'), { target: { value: '+34 600 123' } }); return view
}

describe('P1.5 form validation', () => {
  it.each([['Nombre', ''], ['Nombre', '   '], ['Nombre', 'N'.repeat(121)], ['Teléfono', ''], ['Teléfono', '   '], ['Teléfono', '1'.repeat(41)]])('rejects %s invalid value %s', async (field, value) => {
    await form(); fireEvent.change(screen.getByLabelText(field), { target: { value } }); fireEvent.click(confirm())
    expect(posts()).toHaveLength(0); expect(screen.getByRole('alert')).toBeTruthy()
  })
  it('trims edges, preserves internal content and full timestamps, accepts limits', async () => {
    await form(); const name = 'A '.repeat(59) + 'AB'; const phone = '+34 ' + '1'.repeat(36)
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: `  ${name}  ` } })
    fireEvent.change(screen.getByLabelText('Teléfono'), { target: { value: ` ${phone} ` } })
    fireEvent.click(confirm()); await screen.findByRole('heading', { name: 'Cita reservada.' })
    expect(JSON.parse(String(posts()[0][1]?.body))).toMatchObject({ ...payload, client_name: name, client_phone: phone })
  })
  it.each(['', '2026-02-30', 'garbage'])('rejects invalid date %s in UI and API before fetching', async (value) => {
    await open(); fireEvent.click(next())
    const input = screen.getByLabelText('Fecha de la cita'); input.setAttribute('type', 'text')
    fireEvent.change(input, { target: { value } }); expect(next().disabled).toBe(true)
    const count = fetchMock.mock.calls.length
    await expect(getAvailability(7, 11, value)).rejects.toThrow('fecha válida'); expect(fetchMock).toHaveBeenCalledTimes(count)
    expect(validCalendarDate(value)).toBe(false)
  })
  it('rejects a service removed from the current catalog at confirmation', async () => {
    const view = await form(); view.rerender(<BookingFlow services={[]} initialService={7} onClose={onClose} />)
    expect(next().disabled).toBe(true); expect(posts()).toHaveLength(0)
  })
  it.each([{ barbers: [] }, { barbers: [{ id: -1, name: 'Invalid' }] }, { barbers: [{ id: '11', name: 'Invalid' }] }])('does not continue with invalid/unavailable barbers %j', async ({ barbers }) => {
    overrides['/api/barbers'] = async () => json(barbers)
    render(<BookingFlow services={services} initialService={7} onClose={onClose} />)
    await screen.findByRole('button', { name: 'Continuar' }); expect(next().disabled).toBe(true)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/availability'))).toBe(false)
  })
  it.each(['not-a-date', '2026-10-05T10:30:00', '2026-02-30T10:30:00Z', '2026-10-05T24:00:00Z'])('never selects or formats malformed slot %s', async (starts_at) => {
    overrides['/api/availability'] = async () => json({ slots: [{ ...slot, starts_at }] })
    await slots(); await screen.findByText('No hay horarios disponibles para este día.')
    expect(next().disabled).toBe(true); expect(posts()).toHaveLength(0)
  })
  it.each([start, '2026-10-05T10:00:00-05:00'])('rejects empty or inverted interval ending %s', async (ends_at) => {
    overrides['/api/availability'] = async () => json({ slots: [{ ...slot, ends_at }] })
    await slots(); await screen.findByText('No hay horarios disponibles para este día.')
    expect(next().disabled).toBe(true); expect(posts()).toHaveLength(0)
  })

})

describe('P1.5 error contracts and booking recovery', () => {
  it.each([
    [404, { detail: 'secret-resource-path' }], [409, { detail: 'other conflict' }],
    [422, { detail: 'Traceback secret-password' }],
    [422, { detail: [{ loc: ['body', 'client_name'], type: 'string_too_long', msg: 'secret-msg', input: 'secret-input', ctx: { secret: true } }] }],
    [500, { detail: { error: 'secret-password', stack: 'Traceback' } }],
  ])('normalizes status %i to typed safe detail', async (status, body) => {
    post = async () => json(body, status as number)
    try { await createAppointment(payload); expect.fail('must reject') } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      const apiError = error as ApiError
      expect(apiError.status).toBe(status); expect(typeof apiError.detail).toBe('string')
      expect(JSON.stringify(apiError)).not.toMatch(/secret|Traceback|object Object/)
      if (status === 422 && Array.isArray(body.detail)) expect(apiError.validation).toEqual([{ field: 'client_name', type: 'string_too_long', message: 'Nombre: máximo 120 caracteres.' }])
    }
  })
  it.each([404, 422, 500])('renders safe error for HTTP %i without retrying POST', async (status) => {
    post = async () => json({ detail: [{ loc: ['body', 'client_phone'], msg: 'secret', type: 'value_error', input: 'secret' }] }, status)
    await form(); fireEvent.click(confirm()); const alert = await screen.findByRole('alert')
    expect(alert.textContent).not.toMatch(/object Object|secret/); expect(posts()).toHaveLength(1)
    expect(screen.getByLabelText<HTMLInputElement>('Nombre').value).toBe('Cliente')
  })
  it('renders a safe 422 string without exposing arbitrary server content', async () => {
    post = async () => json({ detail: 'Traceback secret-password' }, 422)
    await form(); fireEvent.click(confirm())
    expect((await screen.findByRole('alert')).textContent).toBe('Revisa los datos y las selecciones de la reserva.')
    expect(posts()).toHaveLength(1)
  })
  it('treats a malformed JSON success as an uncertain POST outcome', async () => {
    post = async () => json({ detail: 'secret' }, 201)
    await form(); fireEvent.click(confirm())
    expect((await screen.findByRole('alert')).textContent).toContain('podría haberse registrado')
    expect(posts()).toHaveLength(1)
  })
  it('409 clears selected slot, refreshes availability and preserves personal data', async () => {
    post = async () => json({ detail: 'Some different conflict' }, 409)
    await form(); fireEvent.click(confirm()); await screen.findByRole('heading', { name: 'Escoge una hora' })
    expect(screen.getByRole('alert').textContent).toContain('no está disponible')
    expect(screen.getByRole('alert').textContent).not.toMatch(/otro cliente|acaba de/)
    const button = await screen.findByRole('button', { name: '10:30' }); expect(button.classList.contains('selected')).toBe(false)
    expect(next().disabled).toBe(true); expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/availability'))).toHaveLength(2)
    fireEvent.click(button); fireEvent.click(next()); expect(screen.getByLabelText<HTMLInputElement>('Nombre').value).toBe('Cliente')
    expect(screen.getByLabelText<HTMLInputElement>('Teléfono').value).toBe('+34 600 123'); expect(posts()).toHaveLength(1)
  })
  it.each(['network', 'non-json', 'non-json-error'])('%s does not assert failure to create and never retries', async (failure) => {
    post = async () => { if (failure === 'network') throw new TypeError('secret connection'); return new Response('<html>secret Traceback</html>', { status: failure === 'non-json-error' ? 502 : 201 }) }
    await form(); fireEvent.click(confirm()); const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('podría haberse registrado'); expect(alert.textContent).not.toMatch(/secret|Traceback|no se creó|object Object/)
    expect(posts()).toHaveLength(1)
  })
  it('blocks synchronous double click, close, back, inputs and unload during POST', async () => {
    let resolve!: (value: Response) => void
    post = () => new Promise((done) => { resolve = done })
    await form(); const button = confirm()
    act(() => { button.click(); button.click() }); expect(posts()).toHaveLength(1)
    const back = screen.getByRole<HTMLButtonElement>('button', { name: /Atrás/ }); const close = screen.getByRole<HTMLButtonElement>('button', { name: 'Cerrar reserva' })
    expect(back.disabled).toBe(true); expect(close.disabled).toBe(true)
    fireEvent.click(back); fireEvent.click(close); expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByLabelText<HTMLInputElement>('Nombre').disabled).toBe(true)
    const unload = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(unload); expect(unload.defaultPrevented).toBe(true)
    await act(async () => resolve(json({ ...payload, id: 80, ends_at: slot.ends_at, status: 'pending' }, 201)))
    await screen.findByRole('heading', { name: 'Cita reservada.' }); expect(posts()).toHaveLength(1)
  })
  it('keeps the submitted summary when catalog and business date change during POST', async () => {
    let resolve!: (value: Response) => void
    post = () => new Promise((done) => { resolve = done })
    const view = await form(); fireEvent.click(confirm())
    vi.setSystemTime(new Date('2026-10-06T05:00:00Z'))
    fireEvent.focus(window)
    view.rerender(<BookingFlow services={[]} initialService={7} onClose={onClose} />)
    expect(screen.getByText('Servicio API')).toBeTruthy()
    expect(screen.getByText('10:30')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Un último detalle' })).toBeTruthy()
    expect(JSON.parse(String(posts()[0][1]?.body)).starts_at).toBe(start)
    await act(async () => resolve(json({ ...payload, id: 80, ends_at: slot.ends_at, status: 'pending' }, 201)))
    await screen.findByRole('heading', { name: 'Cita reservada.' })
    expect(screen.getByText('Servicio API')).toBeTruthy()
  })

})

describe('P1.5 explicit GET retries', () => {
  it.each([
    ['/api/barbers', 'Reintentar barberos', [{ id: 11, name: 'Barbero API' }]],
    ['/api/business-config', 'Reintentar configuración', config],
  ])('retries %s without reopening the booking', async (path, label, body) => {
    let fail = true
    overrides[String(path)] = async () => fail ? json({}, 503) : json(body)
    render(<BookingFlow services={services} initialService={7} onClose={onClose} />)
    await screen.findByRole('alert'); fail = false; fireEvent.click(screen.getByRole('button', { name: String(label) }))
    await waitFor(() => expect(next().disabled).toBe(false)); expect(screen.queryByRole('alert')).toBeNull()
  })
  it('retries availability after failure without retaining old slots', async () => {
    let fail = true; overrides['/api/availability'] = async () => fail ? json({}, 503) : json({ slots: [slot] })
    await slots(); await screen.findByRole('alert'); expect(screen.queryByRole('button', { name: '10:30' })).toBeNull()
    fail = false; fireEvent.click(screen.getByRole('button', { name: 'Reintentar horarios' }))
    await screen.findByRole('button', { name: '10:30' }); expect(next().disabled).toBe(true)
  })
  it.each([{}, null, { timezone: '' }, { timezone: 'Not/AZone' }])('rejects missing or invalid business configuration %j without a fallback', async (value) => {
    let fail = true
    overrides['/api/business-config'] = async () => json(fail ? value : config)
    render(<BookingFlow services={services} initialService={7} onClose={onClose} />)
    await screen.findByRole('alert'); expect(next().disabled).toBe(true)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/availability'))).toBe(false)
    fail = false; fireEvent.click(screen.getByRole('button', { name: 'Reintentar configuración' }))
    await waitFor(() => expect(next().disabled).toBe(false))
  })
  it('retries the public homepage schedule', async () => {
    let fail = true; overrides['/api/business-config'] = async () => fail ? json({}, 503) : json(config)
    render(<HomePage />); await screen.findByText('No se pudo cargar el horario de atención.')
    fail = false; fireEvent.click(screen.getByRole('button', { name: 'Reintentar horario de atención' }))
    expect(await screen.findByText('10:00–21:00')).toBeTruthy()
  })
})
