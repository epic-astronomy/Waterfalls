// Times are kept in UTC everywhere, in the API and in queries. This only
// changes how they are shown and entered: in UTC or in the browser's time zone.
export type TimeZoneMode = 'utc' | 'local'

const STORAGE_KEY = 'epic-time-zone'

// UTC ms of an API time ("2026-10-14T18:57:02.932", naive UTC), a Date or ms
function toMs(t: string | number | Date) {
  if (typeof t == 'number') return t
  if (t instanceof Date) return t.getTime()
  const iso = String(t).trim().replace(' ', 'T').replace(/(\.\d{3})\d*/, '$1').replace(/(Z|[+-]00:?00)$/, '')
  return Date.parse(iso + 'Z')
}

export function useTimeZone() {
  const mode = useState<TimeZoneMode>('time-zone', () => 'utc')
  const local = computed(() => mode.value == 'local')

  // wall-clock time in the chosen zone, as an ISO string without a zone
  const wall = (ms: number) => new Date(local.value ? ms - new Date(ms).getTimezoneOffset() * 6e4 : ms).toISOString().slice(0, 23)

  const zoneName = (t: string | number | Date = Date.now()) => {
    if (!local.value) return 'UTC'
    const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(new Date(toMs(t)))
    return parts.find(p => p.type == 'timeZoneName')?.value ?? 'local'
  }

  return {
    mode,
    local,
    zoneName,
    setMode(m: TimeZoneMode) {
      mode.value = m
      try { localStorage.setItem(STORAGE_KEY, m) } catch { }
    },
    restore() {
      try { if (localStorage.getItem(STORAGE_KEY) == 'local') mode.value = 'local' } catch { }
    },
    // "2026-10-14 18:57:44"
    dateTime: (t: string | number | Date) => wall(toMs(t)).replace('T', ' ').slice(0, 19),
    // "18:57:44"
    clock: (t: string | number | Date) => wall(toMs(t)).slice(11, 19),
    // for plot axes, to the millisecond
    plotTime: (t: string | number | Date) => wall(toMs(t)).replace('T', ' '),
    // a datetime-local input value from an API time, and back
    toInput: (t: string) => (t ? wall(toMs(t)).slice(0, 19) : ''),
    fromInput: (v: string) => {
      if (!v) return ''
      const ms = local.value ? new Date(v).getTime() : toMs(v)
      return new Date(ms).toISOString().slice(0, 19)
    }
  }
}
