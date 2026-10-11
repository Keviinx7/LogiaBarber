import { ArrowLeft, ArrowRight, Check } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, validCalendarDate, validSlotTimestamp, createAppointment, getAvailability, getBarbers, getBusinessConfig, type Appointment, type AvailabilitySlot, type Barber } from '../api/client'
import type { Service } from '../api/types'
import { formatServicePrice } from './ServiceCard'
import { businessDate, businessTime, displayCalendarDate as displayDate } from '../utils/businessTime'

const steps = ['Servicio', 'Barbero', 'Fecha', 'Hora', 'Tus datos']
type BookingFlowProps = {
  services: readonly Service[]
  initialService?: number
  catalogLoading?: boolean
  catalogError?: string
  onRetryServices?: () => void
  onClose: () => void
}

export function BookingFlow({ services, initialService, catalogLoading = false, catalogError = '', onRetryServices, onClose }: BookingFlowProps) {
  const [step, setStep] = useState(0)
  const [barbers, setBarbers] = useState<Barber[]>([])
  const [serviceId, setServiceId] = useState<number>()
  const [barberId, setBarberId] = useState<number>()
  const [timezone, setTimezone] = useState('')
  const [configLoading, setConfigLoading] = useState(true)
  const [configError, setConfigError] = useState('')
  const [today, setToday] = useState('')
  const [date, setDate] = useState('')
  const [availability, setAvailability] = useState<{
    key: string; slots: AvailabilitySlot[]; loading: boolean; error: string
  }>()
  const [selection, setSelection] = useState<{ key: string; starts_at: string }>()
  const [barbersLoading, setBarbersLoading] = useState(true)
  const [barbersError, setBarbersError] = useState('')
  const [barbersAttempt, setBarbersAttempt] = useState(0)
  const [configAttempt, setConfigAttempt] = useState(0)
  const [availabilityAttempt, setAvailabilityAttempt] = useState(0)
  const [loading, setLoading] = useState(false)
  const submitting = useRef(false)
  const [error, setError] = useState('')
  const [submittedSummary, setSubmittedSummary] = useState<{ service: Service; barber: string; date: string; start: string }>()
  const [success, setSuccess] = useState<Appointment>()
  const [name, setName] = useState(''); const [phone, setPhone] = useState(''); const [notes, setNotes] = useState('')
  const activeServices = useMemo(() => services.filter((service) => service.is_active), [services])
  const chosen = useMemo(() => activeServices.find((item) => item.id === serviceId), [activeServices, serviceId])
  // Results and selection belong to one service/barber/calendar-date query.
  // Key checks invalidate them during render, before effects or late responses.
  const validBarber = barbers.some((barber) => barber.id === barberId)
  const validDate = validCalendarDate(date)
  const queryKey = `${serviceId ?? ''}/${barberId ?? ''}/${date}`
  const currentAvailability = availability?.key === queryKey ? availability : undefined
  const slots = currentAvailability?.slots ?? []
  const slotsLoading = currentAvailability?.loading ?? false
  const availabilityError = currentAvailability?.error ?? ''
  const selectedStart = selection?.key === queryKey && slots.some((slot) =>
    slot.available === true && validSlotTimestamp(slot.starts_at) && validSlotTimestamp(slot.ends_at) && Date.parse(slot.ends_at) > Date.parse(slot.starts_at) && slot.starts_at === selection.starts_at) ? selection.starts_at : ''
  const summaryService = (loading || success) && submittedSummary ? submittedSummary.service : chosen
  const summaryDate = loading && submittedSummary ? submittedSummary.date : date
  const summaryStart = loading && submittedSummary ? submittedSummary.start : selectedStart
  const summaryBarber = loading && submittedSummary ? submittedSummary.barber : barbers.find((barber) => barber.id === barberId)?.name
  const setSelectedStart = (starts_at: string) => setSelection(starts_at ? { key: queryKey, starts_at } : undefined)
  useEffect(() => {
    setSelection(undefined)
    setAvailability(undefined)
    setError('')
  }, [queryKey])
  useEffect(() => {
    if (submitting.current) return
    const valid = activeServices.find((service) => service.id === initialService)
    setServiceId(valid?.id)
    setStep(valid ? 1 : 0)
  }, [activeServices, initialService])
  useEffect(() => {
    let current = true
    setBarbersLoading(true)
    setBarbersError('')
    setBarbers([])
    setBarberId(undefined)
    getBarbers().then((data) => {
      if (current) { setBarbers(data); setBarberId(data[0]?.id) }
    }).catch(() => { if (current) setBarbersError('No se pudo cargar la lista de barberos.') })
      .finally(() => { if (current) setBarbersLoading(false) })
    return () => { current = false }
  }, [barbersAttempt])
  useEffect(() => {
    let current = true
    setConfigLoading(true)
    setConfigError('')
    getBusinessConfig().then(({ timezone: zone }) => {
      if (!current) return
      const currentDay = businessDate(new Date(), zone)
      setTimezone(zone)
      setToday(currentDay)
      setDate(currentDay)
    }).catch(() => {
      if (current) setConfigError('No se pudo cargar una zona horaria válida del negocio. Reintenta la carga.')
    }).finally(() => { if (current) setConfigLoading(false) })
    return () => { current = false }
  }, [configAttempt])
  useEffect(() => {
    if (!timezone) return
    const refreshDay = () => setToday(businessDate(new Date(), timezone))
    const onVisibility = () => { if (document.visibilityState === 'visible') refreshDay() }
    window.addEventListener('focus', refreshDay)
    document.addEventListener('visibilitychange', onVisibility)
    const timer = window.setInterval(refreshDay, 30_000)
    refreshDay()
    return () => {
      window.removeEventListener('focus', refreshDay)
      document.removeEventListener('visibilitychange', onVisibility)
      window.clearInterval(timer)
    }
  }, [timezone])
  useEffect(() => {
    if (validDate && today && date < today && !success && !submitting.current) {
      setDate(today)
      setSelectedStart('')
      setAvailability(undefined)
      setStep((current) => current > 2 ? 2 : current)
    }
  }, [date, today, success])
  useEffect(() => {
    if (step !== 3 || !chosen || !barberId || !validBarber || !validDate || date < today || !timezone) return
    const controller = new AbortController()
    setSelection(undefined)
    setAvailability({ key: queryKey, slots: [], loading: true, error: '' })
    getAvailability(chosen.id, barberId, date, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setAvailability({ key: queryKey, slots: data.slots.filter((slot) => slot.available === true && validSlotTimestamp(slot.starts_at) && validSlotTimestamp(slot.ends_at) && Date.parse(slot.ends_at) > Date.parse(slot.starts_at)), loading: false, error: '' })
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const aborted = typeof err === 'object' && err !== null && 'name' in err && err.name === 'AbortError'
        setAvailability({ key: queryKey, slots: [], loading: false,
          error: aborted ? '' : 'No se pudo cargar la disponibilidad.' })
      })
    return () => { controller.abort() }
  }, [step, chosen, barberId, date, today, timezone, queryKey, availabilityAttempt, validBarber, validDate])
  useEffect(() => {
    if (!loading) return
    const protectNavigation = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', protectNavigation)
    return () => window.removeEventListener('beforeunload', protectNavigation)
  }, [loading])
  const submit = async () => {
    if (submitting.current) return
    if (!name.trim() || !phone.trim() || !selectedStart || !chosen || !barberId || !validBarber || !validDate || catalogLoading || catalogError) {
      setError('Completa tus datos y selecciona un horario.')
      return
    }
    if (name.trim().length > 120 || phone.trim().length > 40) {
      setError('El nombre admite máximo 120 caracteres y el teléfono máximo 40.')
      return
    }
    // Compare instants only; preserve the server's original timestamp for POST.
    if (!(new Date(selectedStart).getTime() > Date.now())) {
      setSelection(undefined)
      setAvailability(undefined)
      setError('Este horario ya venció. Consulta y elige otro horario.')
      setStep(3)
      return
    }
    setSubmittedSummary({ service: chosen, barber: barbers.find((barber) => barber.id === barberId)!.name, date, start: selectedStart })
    submitting.current = true
    setLoading(true)
    setError('')
    try {
      const appointment = await createAppointment({
        client_name: name.trim(), client_phone: phone.trim(), service_id: chosen.id,
        barber_id: barberId, starts_at: selectedStart, notes: notes.trim() || undefined,
      })
      setSuccess(appointment)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setSelection(undefined)
        setAvailability(undefined)
        setAvailabilityAttempt((attempt) => attempt + 1)
        setStep(3)
        setError(err.detail)
      } else if (err instanceof ApiError && err.uncertain) {
        setError('No pudimos confirmar el resultado de la solicitud. La reserva podría haberse registrado. Verifica con Logia Barber antes de volver a enviarla.')
      } else {
        setError(err instanceof ApiError ? err.detail : 'No se pudo completar la solicitud. Revisa los datos e inténtalo de nuevo.')
      }
    } finally { submitting.current = false; setLoading(false) }
  }
  const next = () => {
    if (submitting.current) return
    if (!chosen || catalogLoading || catalogError) { setStep(0); return }
    if (!timezone || configLoading || configError) return
    const currentDay = businessDate(new Date(), timezone)
    setToday(currentDay)
    if (!validDate) { setError('Selecciona una fecha válida.'); setStep(2); return }
    if (date < currentDay) {
      setDate(currentDay)
      setSelectedStart('')
      setAvailability(undefined)
      if (step > 2) setStep(2)
      return
    }
    if (step >= 1 && (!validBarber || barbersLoading || barbersError)) { setStep(1); return }
    if (step >= 3 && !selectedStart) return
    return step < 4 ? setStep(step + 1) : submit()
  }
  if (success) return <section className="booking-panel success-panel"><div className="success-icon"><Check /></div><span className="eyebrow text-gold">Logia Barber · Confirmación</span><h2>Cita reservada<span className="text-gold">.</span></h2><p>Tu lugar está apartado. Te esperamos para disfrutar tu próximo corte.</p><div className="booking-summary"><div><span>Servicio</span><strong>{summaryService?.name}</strong></div><div><span>Fecha</span><strong>{displayDate(businessDate(new Date(success.starts_at), timezone))}</strong></div><div><span>Hora</span><strong>{businessTime(success.starts_at, timezone)}</strong></div><div><span>Duración</span><strong>{summaryService?.duration_minutes} min</strong></div></div><button className="button" onClick={onClose}>Volver al inicio <ArrowRight size={17} /></button></section>
  return <section className="booking-panel" aria-label="Flujo de reserva"><div className="booking-head"><div><span className="eyebrow text-gold">Reserva tu momento</span><h2>Agenda tu cita<span className="text-gold">.</span></h2></div><button className="close-button" disabled={loading} onClick={() => { if (!submitting.current) onClose() }} aria-label="Cerrar reserva">×</button></div><div className="stepper">{steps.map((item, index) => <div key={item} className={index <= step ? 'step active' : 'step'}><span>{index < step ? <Check size={13} /> : index + 1}</span><label>{item}</label></div>)}</div>{configError && <div><p className="api-error" role="alert">{configError}</p><button className="button" disabled={loading} onClick={() => setConfigAttempt((attempt) => attempt + 1)}>Reintentar configuración</button></div>}{error && <p className="api-error" role="alert">{error}</p>}{availabilityError && <div><p className="api-error" role="alert">{availabilityError}</p><button className="button" onClick={() => setAvailabilityAttempt((attempt) => attempt + 1)}>Reintentar horarios</button></div>}<div className="booking-content">
    {step === 0 && <div><div className="section-heading"><span className="eyebrow">Paso 01</span><h3>Elige tu servicio</h3><p>Servicios disponibles en Logia Barber.</p>{!catalogLoading && !catalogError && initialService !== undefined && !activeServices.some((service) => service.id === initialService) && <p role="status">El servicio preseleccionado ya no está disponible. Elige un servicio válido.</p>}</div>{catalogLoading ? <p className="state-message" role="status">Cargando servicios...</p> : catalogError ? <div><p className="api-error" role="alert">{catalogError}</p>{onRetryServices && <button className="button" onClick={onRetryServices}>Reintentar</button>}</div> : activeServices.length ? <div className="choice-grid">{activeServices.map((service) => <button key={service.id} className={serviceId === service.id ? 'choice-card selected' : 'choice-card'} aria-pressed={serviceId === service.id} onClick={() => setServiceId(service.id)}><span>{service.name}</span><small>{service.duration_minutes} min · {formatServicePrice(service.price)}</small>{serviceId === service.id && <Check size={17} />}</button>)}</div> : <p className="state-message">No hay servicios disponibles.</p>}</div>}
    {step === 1 && <div><div className="section-heading"><span className="eyebrow">Paso 02</span><h3>Elige tu barbero</h3><p>Selecciona quién te atenderá.</p></div>{barbersLoading ? <p role="status">Cargando barberos...</p> : barbersError ? <div><p role="alert" className="api-error">{barbersError}</p><button className="button" onClick={() => setBarbersAttempt((attempt) => attempt + 1)}>Reintentar barberos</button></div> : !barbers.length ? <p role="status">No hay barberos disponibles.</p> : <div className="choice-grid">{barbers.map((barber) => <button key={barber.id} className={barberId === barber.id ? 'choice-card selected' : 'choice-card'} onClick={() => setBarberId(barber.id)}><span>{barber.name}</span><small>Barbero de Logia Barber</small>{barberId === barber.id && <Check size={17} />}</button>)}</div>}</div>}
    {step === 2 && <div><div className="section-heading"><span className="eyebrow">Paso 03</span><h3>Selecciona una fecha</h3><p>Elige el día que mejor te funcione.</p></div><label className="date-field">Fecha de la cita<input type="date" value={date} min={today} onChange={(event) => { setDate(event.target.value); setSelectedStart('') }} /></label></div>}
    {step === 3 && <div><div className="section-heading"><span className="eyebrow">Paso 04</span><h3>Escoge una hora</h3><p>{validDate ? displayDate(date) : 'Selecciona una fecha válida'} · {chosen?.duration_minutes} min</p></div>{slotsLoading ? <p className="state-message">Cargando horarios...</p> : availabilityError ? null : slots.length ? <div className="time-grid">{slots.map((slot) => <button key={slot.starts_at} className={selectedStart === slot.starts_at ? 'time-slot selected' : 'time-slot'} onClick={() => { setSelectedStart(slot.starts_at); setError('') }}>{businessTime(slot.starts_at, timezone)}</button>)}</div> : <p className="state-message">No hay horarios disponibles para este día.</p>}</div>}
    {step === 4 && <div><div className="section-heading"><span className="eyebrow">Paso 05</span><h3>Un último detalle</h3><p>Déjanos tus datos para confirmar la cita.</p></div><div className="customer-grid"><label>Nombre<input disabled={loading} required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} placeholder="Tu nombre" /></label><label>Teléfono<input disabled={loading} required maxLength={40} value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="099 000 0000" type="tel" /></label><label className="full-label">Notas <span>(opcional)</span><textarea disabled={loading} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="¿Algo que debamos saber?" rows={3} /></label></div><div className="booking-summary compact"><div><span>Servicio</span><strong>{summaryService?.name}</strong></div><div><span>Barbero</span><strong>{summaryBarber}</strong></div><div><span>Fecha</span><strong>{validCalendarDate(summaryDate) ? displayDate(summaryDate) : 'Selecciona una fecha válida'}</strong></div><div><span>Hora</span><strong>{summaryStart && businessTime(summaryStart, timezone)}</strong></div></div></div>}
  </div><div className="booking-actions">{step > 0 && <button className="back-button" disabled={loading} onClick={() => { if (!submitting.current) setStep(step - 1) }}><ArrowLeft size={16} /> Atrás</button>}<button className="button" disabled={loading || barbersLoading || (step === 3 && slotsLoading) || configLoading || !!configError || !timezone || !validDate || date < today || catalogLoading || !!catalogError || !chosen || (step >= 1 && (!validBarber || !!barbersError)) || (step >= 3 && !selectedStart)} onClick={next}>{loading || barbersLoading || (step === 3 && slotsLoading) || configLoading || catalogLoading ? 'Cargando...' : step === 4 ? 'Confirmar cita' : 'Continuar'} <ArrowRight size={17} /></button></div></section>
}
