// JSON returned by ServiceResponse; Pydantic serializes Decimal as a string.
export type Service = {
  id: number
  name: string
  description: string | null
  price: string
  duration_minutes: number
  is_active: boolean
  created_at: string
  updated_at: string
}
export type BusinessConfig = {
  timezone: string
  opening_time: string
  closing_time: string
  lunch_start: string
  lunch_end: string
  working_days: number[]
}

// Calendar date (YYYY-MM-DD), distinct from the offset-bearing slot instants.
export type AvailabilityResponse = {
  date: string
  service_id: number
  barber_id: number
  slots: AvailabilitySlot[]
}

export type AvailabilitySlot = {
  starts_at: string
  ends_at: string
  available: boolean
}
