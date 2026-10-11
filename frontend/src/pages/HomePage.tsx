import { ArrowDown, ArrowUpRight, Camera, MapPin, MessageCircle, Phone, Scissors, Star } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getBusinessConfig, getServices } from '../api/client'
import type { BusinessConfig, Service } from '../api/types'
import { BookingFlow } from '../components/BookingFlow'
import { Navbar } from '../components/Navbar'
import { ServiceCard } from '../components/ServiceCard'
import { gallery } from '../data/mockData'

const dayNames = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

export function HomePage() {
  const [bookingOpen, setBookingOpen] = useState(false)
  const [initialService, setInitialService] = useState<number>()
  const [services, setServices] = useState<Service[]>([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [catalogAttempt, setCatalogAttempt] = useState(0)
  const retryServices = () => setCatalogAttempt((attempt) => attempt + 1)
  useEffect(() => {
    let current = true
    setCatalogLoading(true)
    setCatalogError('')
    getServices().then((data) => {
      if (current) setServices(data)
    }).catch(() => {
      if (current) {
        setServices([])
        setCatalogError('No se pudo cargar el catálogo de servicios.')
      }
    }).finally(() => { if (current) setCatalogLoading(false) })
    return () => { current = false }
  }, [catalogAttempt])
  const [businessConfig, setBusinessConfig] = useState<BusinessConfig>()
  const [scheduleError, setScheduleError] = useState(false)
  const [scheduleAttempt, setScheduleAttempt] = useState(0)
  useEffect(() => {
    let current = true
    setScheduleError(false)
    setBusinessConfig(undefined)
    getBusinessConfig().then((config) => {
      const times = [config.opening_time, config.closing_time, config.lunch_start, config.lunch_end]
      if (!times.every((value) => typeof value === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(value)) ||
          !Array.isArray(config.working_days) || !config.working_days.length ||
          !config.working_days.every((day) => Number.isInteger(day) && day >= 0 && day < dayNames.length) ||
          new Set(config.working_days).size !== config.working_days.length) {
        throw new Error('Horario público inválido')
      }
      if (current) setBusinessConfig(config)
    }).catch(() => { if (current) setScheduleError(true) })
    return () => { current = false }
  }, [scheduleAttempt])
  const openBooking = (service?: number) => { setInitialService(service); setBookingOpen(true) }
  return <main>
    <Navbar onBook={() => openBooking()} />
    <section className="hero" id="inicio"><div className="hero-copy"><div className="hero-kicker"><span className="line" /> Barbería contemporánea <span className="line" /></div><h1>Tu estilo.<br /><em>Tu momento.</em></h1><p>Un corte preciso, una pausa para ti. Descubre una experiencia de barbería hecha con intención.</p><div className="hero-actions"><button className="button" onClick={() => openBooking()}>Reservar cita <ArrowUpRight size={17} /></button><a href="#servicios" className="ghost-button">Ver servicios <ArrowDown size={16} /></a></div></div><div className="hero-visual"><div className="visual-label"><span>01</span><span>Tradición<br />contemporánea</span></div><div className="visual-stamp"><Scissors size={20} /><span>Est. 2024</span></div></div><div className="scroll-note"><span className="scroll-line" /> Desplázate para descubrir</div></section>
    <section className="intro section-wrap"><div className="intro-number">01 <span>/</span> 05</div><div><span className="eyebrow">La experiencia Logia Barber</span><h2>Más que un corte,<br /><em>un ritual.</em></h2></div><p className="intro-text">Creemos que los pequeños detalles hacen la diferencia. Un espacio tranquilo, manos expertas y el tiempo que mereces para verte y sentirte mejor.</p></section>
    <section className="services-section section-wrap" id="servicios"><div className="section-header"><div><span className="eyebrow">Nuestros servicios</span><h2>Lo esencial,<br /><em>bien hecho.</em></h2></div><p>Servicios pensados para tu ritmo, ejecutados con precisión y cuidado.</p></div>{catalogLoading ? <p className="state-message" role="status">Cargando servicios...</p> : catalogError ? <div><p className="api-error" role="alert">{catalogError}</p><button className="button" onClick={retryServices}>Reintentar</button></div> : services.length === 0 ? <p className="state-message" role="status">No hay servicios disponibles.</p> : <div className="services-grid">{services.map((service) => <ServiceCard service={service} key={service.id} onBook={openBooking} />)}</div>}</section>
    <section className="process-section section-wrap"><div className="section-header"><div><span className="eyebrow">Simple por diseño</span><h2>Tu cita en<br /><em>cuatro pasos.</em></h2></div><p>Sin llamadas, sin esperas. Elige cuándo y cómo quieres tu próximo corte.</p></div><div className="process-grid">{['Elige servicio', 'Selecciona fecha', 'Escoge hora', 'Confirma'].map((item, i) => <div className="process-item" key={item}><span className="process-number">0{i + 1}</span><div><h3>{item}</h3><p>{['Encuentra el servicio que va contigo.', 'Dinos qué día te funciona mejor.', 'Reserva un espacio en tu horario.', 'Déjanos tus datos y listo.'][i]}</p></div><ArrowUpRight size={18} /></div>)}</div></section>
    <section className="gallery-section section-wrap"><div className="section-header"><div><span className="eyebrow">El trabajo habla</span><h2>Detalles que<br /><em>se notan.</em></h2></div><a href="#contacto" className="text-button">Ver galería <ArrowUpRight size={15} /></a></div><div className="gallery-grid">{gallery.map((item, i) => <div key={item.label} className={`gallery-item ${item.className}`}><div className={`gallery-placeholder placeholder-${i + 1}`}><Scissors size={25} /></div><span>{item.label}</span></div>)}</div></section>
    <section className="hours-section section-wrap" aria-label="Horario de atención"><div className="hours-art"><div className="hours-circle"><Scissors size={28} /><span>Tiempo<br />para ti</span></div></div><div className="hours-content"><span className="eyebrow">Visítanos</span><h2>Tu tiempo<br /><em>es ahora.</em></h2><div className="hours-list" aria-live="polite">{businessConfig ? <><div><span>{businessConfig.working_days.length === dayNames.length ? 'Lunes a domingo' : businessConfig.working_days.map((day) => dayNames[day]).join(', ')}</span><strong>{businessConfig.opening_time}–{businessConfig.closing_time}</strong></div><div><span>Almuerzo · sin reservas</span><strong>{businessConfig.lunch_start}–{businessConfig.lunch_end}</strong></div></> : <p>{scheduleError ? 'No se pudo cargar el horario de atención.' : 'Cargando horario de atención...'}</p>}{scheduleError && <button className="button" onClick={() => setScheduleAttempt((attempt) => attempt + 1)}>Reintentar horario de atención</button>}</div><p className="address"><MapPin size={16} /> Av. Principal 123 · Tu ciudad</p></div></section>
    <section className="final-cta"><span className="eyebrow">El siguiente paso es tuyo</span><h2>¿Listo para tu<br /><em>próximo corte?</em></h2><button className="button" onClick={() => openBooking()}>Reservar cita <ArrowUpRight size={17} /></button></section>
    <footer id="contacto"><div className="footer-brand"><a className="brand" href="#inicio"><span className="brand-mark"><Scissors size={16} /></span>Logia <span className="text-gold">Barber</span></a><p>Tradición, precisión<br />y un momento para ti.</p></div><div className="footer-links"><div><span className="eyebrow">Contacto</span><a href="tel:#"><Phone size={15} /> Placeholder teléfono</a><a href="#" onClick={(e) => e.preventDefault()}><MessageCircle size={15} /> WhatsApp placeholder</a></div><div><span className="eyebrow">Síguenos</span><a href="#" onClick={(e) => e.preventDefault()}><Camera size={15} /> Instagram placeholder</a></div></div><div className="footer-bottom"><span>© 2024 Logia Barber</span><span>Hecho con intención <Star size={13} /></span></div></footer>
    {bookingOpen && <div className="booking-overlay" id="reservar"><BookingFlow services={services} catalogLoading={catalogLoading} catalogError={catalogError} onRetryServices={retryServices} initialService={initialService} onClose={() => setBookingOpen(false)} /></div>}
  </main>
}
