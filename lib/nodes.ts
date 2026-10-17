// Each imaging node keeps its own band's data. A node that does not answer
// drops out of a response, which names it and its bands: object responses in
// nodes_missing and bands_missing, list responses in these headers.
import { CHAN_BW_HZ } from '~/lib/ndp'

export interface NodeFlags {
  nodes_missing?: string[]
  bands_missing?: number[]
}

export const MISSING_NODES_HEADER = 'X-EPIC-Nodes-Missing'
export const MISSING_BANDS_HEADER = 'X-EPIC-Bands-Missing'

const list = (v: string | null) => (v ?? '').split(',').map(s => s.trim()).filter(Boolean)

export function flagsFromHeaders(headers: Headers): NodeFlags {
  return {
    nodes_missing: list(headers.get(MISSING_NODES_HEADER)),
    bands_missing: list(headers.get(MISSING_BANDS_HEADER)).map(Number).filter(Number.isFinite)
  }
}

export function anyMissing(flags?: NodeFlags | null): boolean {
  return !!flags?.nodes_missing?.length
}

// A sentence saying which bands are missing, empty when none is. Bands are
// named by their lowest frequency, as in the session list
export function missingNote(flags?: NodeFlags | null): string {
  if (!anyMissing(flags)) return ''
  const mhz = [...new Set(flags!.bands_missing ?? [])].sort((a, b) => a - b)
    .map(c => (c * CHAN_BW_HZ / 1e6).toFixed(3))
  if (!mhz.length) return 'Some bands may be missing because an imaging node did not respond.'
  if (mhz.length == 1) return `The ${mhz[0]} MHz band is missing because its imaging node did not respond.`
  return `The ${mhz.slice(0, -1).join(', ')} and ${mhz[mhz.length - 1]} MHz bands are missing because their imaging nodes did not respond.`
}
