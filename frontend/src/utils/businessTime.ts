/** Calendar date in an explicit business timezone, independent of the device. */
export function businessDate(instant: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone, calendar: 'gregory', numberingSystem: 'latn',
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(instant)
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)!.value
  return `${part('year')}-${part('month')}-${part('day')}`
}

/** Presentation only: never use the formatted hour to construct a timestamp. */
export function businessTime(timestamp: string, timeZone: string): string {
  return new Intl.DateTimeFormat('es-EC', {
    timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(new Date(timestamp))
}

/** Format a calendar date; UTC is only a stable formatting anchor, not its zone. */
export function displayCalendarDate(date: string): string {
  return new Intl.DateTimeFormat('es-EC', {
    timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long',
  }).format(new Date(`${date}T00:00:00Z`))
}
