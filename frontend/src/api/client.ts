import type { AvailabilityResponse, BusinessConfig, Service } from './types'

export type { AvailabilitySlot } from './types'
export type Barber = { id: number; name: string }
export type Appointment = { id: number; client_name: string; client_phone: string; service_id: number; barber_id: number; starts_at: string; ends_at: string; status: string; notes?: string }
const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export type ApiValidationIssue = { field: string; type: string; message: string }
export class ApiError extends Error {
  constructor(public status: number | null, public detail: string, public validation: ApiValidationIssue[] = [], public uncertain = false) {
    super(detail)
    this.name = 'ApiError'
  }
}
const validationFields: Record<string, string> = { client_name: 'Nombre', client_phone: 'Teléfono', service_id: 'Servicio', barber_id: 'Barbero', starts_at: 'Horario', notes: 'Notas' }
function httpError(status: number, body: unknown): ApiError {
  const detail = typeof body === 'object' && body !== null && 'detail' in body ? body.detail : undefined
  const validation: ApiValidationIssue[] = []
  if (status === 422 && Array.isArray(detail)) {
    for (const item of detail) {
      if (typeof item !== 'object' || item === null || !Array.isArray(item.loc)) continue
      const field = item.loc.find((part: unknown) => typeof part === 'string' && Object.hasOwn(validationFields, part))
      if (!field) continue
      // Never expose server input, ctx, arbitrary messages, or unknown locations.
      const type = ['string_too_long', 'string_too_short', 'missing', 'greater_than', 'timezone_aware', 'value_error'].includes(item.type) ? item.type : 'invalid'
      const message = type === 'string_too_long' && (field === 'client_name' || field === 'client_phone')
        ? `${validationFields[field]}: máximo ${field === 'client_name' ? 120 : 40} caracteres.`
        : `${validationFields[field]}: revisa este valor.`
      validation.push({ field, type, message })
    }
  }
  const message = status === 409 ? 'El horario no está disponible. Consulta y elige otro horario.'
    : status === 404 ? 'El recurso solicitado ya no está disponible. Actualiza tu selección.'
    : status === 422 ? (validation.map((item) => item.message).join(' ') || 'Revisa los datos y las selecciones de la reserva.')
    : 'No se pudo completar la solicitud. Inténtalo más tarde.'
  return new ApiError(status, message, validation)
}
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  } catch (error) {
    if (typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError') throw error
    throw new ApiError(null, 'No se pudo conectar con el servidor.', [], options?.method === 'POST')
  }
  if (!response.ok) {
    const error = httpError(response.status, await response.json().catch(() => undefined))
    error.uncertain = options?.method === 'POST' && response.status >= 500
    throw error
  }
  try { return await response.json() as T }
  catch { throw new ApiError(response.status, 'El servidor devolvió una respuesta no válida.', [], options?.method === 'POST') }
}
export function validCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().startsWith(`${value}T`)
}
export function validSlotTimestamp(value: string): boolean {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && validCalendarDate(value.substring(0, 10)) && Number.isFinite(Date.parse(value))
}
function requireId(id: number) {
  if (!Number.isSafeInteger(id) || id <= 0) throw new Error('El ID debe ser un entero positivo.')
}

export async function getServices() {
  const services = await request<Service[]>('/api/services')
  services.forEach((service) => requireId(service.id))
  return services.filter((service) => service.is_active)
}
export async function getBarbers() {
  const barbers = await request<Barber[]>('/api/barbers')
  barbers.forEach((barber) => requireId(barber.id))
  return barbers
}
export async function getBusinessConfig(): Promise<BusinessConfig> {
  const config = await request<BusinessConfig>('/api/business-config')
  if (!config || typeof config.timezone !== 'string' || !config.timezone.trim()) {
    throw new Error('La configuración de zona horaria del negocio es inválida.')
  }
  // Fail explicitly if this browser cannot use the server's timezone.
  new Intl.DateTimeFormat('es-EC', { timeZone: config.timezone }).format()
  return config
}
export async function getAvailability(serviceId: number, barberId: number, date: string, signal?: AbortSignal) {
  requireId(serviceId)
  requireId(barberId)
  if (!validCalendarDate(date)) throw new Error('Selecciona una fecha válida.')
  return request<AvailabilityResponse>(`/api/availability?service_id=${serviceId}&barber_id=${barberId}&date=${date}`, { signal })
}
export async function createAppointment(payload: { client_name: string; client_phone: string; service_id: number; barber_id: number; starts_at: string; notes?: string }) {
  requireId(payload.service_id)
  requireId(payload.barber_id)
  const appointment = await request<Appointment>('/api/appointments', { method: 'POST', body: JSON.stringify(payload) })
  if (!appointment || !Number.isSafeInteger(appointment.id) || !validSlotTimestamp(appointment.starts_at)) {
    throw new ApiError(201, 'El servidor devolvió una confirmación no válida.', [], true)
  }
  return appointment
}
