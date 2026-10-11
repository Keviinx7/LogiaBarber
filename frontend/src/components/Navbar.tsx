import { Menu, Scissors, X } from 'lucide-react'
import { useState } from 'react'

export function Navbar({ onBook }: { onBook: () => void }) {
  const [open, setOpen] = useState(false)
  return <header className="nav-shell">
    <a className="brand" href="#inicio"><span className="brand-mark"><Scissors size={16} /></span><span>Logia <span className="text-gold">Barber</span></span></a>
    <button className="menu-toggle" aria-label={open ? 'Cerrar menú' : 'Abrir menú'} onClick={() => setOpen(!open)}>{open ? <X /> : <Menu />}</button>
    <nav className={open ? 'nav-links is-open' : 'nav-links'} aria-label="Navegación principal">
      <a href="#inicio" onClick={() => setOpen(false)}>Inicio</a><a href="#servicios" onClick={() => setOpen(false)}>Servicios</a><a href="#reservar" onClick={() => setOpen(false)}>Reservar</a><a href="#contacto" onClick={() => setOpen(false)}>Contacto</a>
      <button className="button button-small" onClick={() => { onBook(); setOpen(false) }}>Reservar cita <span>↗</span></button>
    </nav>
  </header>
}
