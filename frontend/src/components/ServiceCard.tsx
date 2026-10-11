import { Clock, ArrowUpRight } from 'lucide-react'
import type { Service } from '../api/types'

export const formatServicePrice = (price: Service['price']) => new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' }).format(Number(price))

export function ServiceCard({ service, onBook }: { service: Service; onBook: (id: number) => void }) {
  return <article className="service-card">
    <div className="service-card-top"><span className="eyebrow">Servicio</span><span className="card-arrow"><ArrowUpRight size={18} /></span></div>
    <div><h3>{service.name}</h3>{service.description && <p>{service.description}</p>}</div>
    <div className="service-meta"><span><Clock size={15} /> {service.duration_minutes} min</span><strong>{formatServicePrice(service.price)}</strong></div>
    <button className="text-button" onClick={() => onBook(service.id)}>Elegir servicio <ArrowUpRight size={15} /></button>
  </article>
}
