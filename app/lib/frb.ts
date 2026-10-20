import type { WatchListItem } from '~/types'

// Cold-plasma dispersion delay constant in s MHz^2 cm^3 / pc
export const K_DM = 4148.808

export interface FrbParams {
  dm: number,
  dmErr: number,
  t0: number // arrival time at infinite frequency, UTC ms
}

// CHIME/FRB publishes the topocentric arrival at 400 MHz (timestamp_utc), the
// bottom of its band, where it is measured; its time at infinite frequency is
// derived from that with CHIME's DM, so derive it here the same way
export const CHIME_REF_MHZ = 400

// UTC ms from the API ("2026-10-14T18:57:02.932") or a VOEvent
// ("2026-10-14 18:57:02.931651+00:00"), both of which are in UTC
export function utcMs(t: string) {
  const iso = t.trim().replace(' ', 'T').replace(/(\.\d{3})\d*/, '$1').replace(/(Z|[+-]00:?00)$/, '')
  return Date.parse(iso + 'Z')
}

export const isFrbSource = (src?: WatchListItem) => src?.event_type == 'FRB detection'

function voeventParam(voevent: string, name: string) {
  return voevent.match(new RegExp(`<Param name="${name}" value="([^"]*)"`))?.[1]
}

export function frbParams(src?: WatchListItem): FrbParams | null {
  if (!isFrbSource(src)) return null
  const voevent = String(src!.voevent ?? '')
  const dm = parseFloat(voeventParam(voevent, 'dm') ?? '')
  if (!isFinite(dm)) return null
  const tRef = voeventParam(voevent, 'timestamp_utc')
  return {
    dm,
    dmErr: parseFloat(voeventParam(voevent, 'dm_error') ?? '') || 0,
    t0: tRef ? utcMs(tRef) - 1e3 * K_DM * dm / CHIME_REF_MHZ ** 2
      : utcMs(voeventParam(voevent, 'timestamp_utc_inf_freq') ?? String(src!.event_time))
  }
}

// Arrival time (UTC ms) of the burst at a frequency in MHz
export const arrivalMs = (p: FrbParams, fMHz: number, dm = p.dm) => p.t0 + 1e3 * K_DM * dm / fMHz ** 2

// Frequency (MHz) the burst is at, at a given time
export const freqAtMs = (p: FrbParams, tMs: number) =>
  tMs <= p.t0 ? Infinity : Math.sqrt(K_DM * p.dm / ((tMs - p.t0) / 1e3))
