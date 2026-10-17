// Each imaging node keeps its own band's recent data, and an archive on the
// head node the older data. A node that does not answer drops out of a
// response, which names it and its bands, and an archive that does not answer
// is flagged with the time before which data are missing: object responses in
// nodes_missing, bands_missing, archive_missing and archive_before, list
// responses in these headers.
import { CHAN_BW_HZ } from '~/lib/ndp'

export interface NodeFlags {
  nodes_missing?: string[]
  bands_missing?: number[]
  archive_missing?: boolean
  archive_before?: string | null
}

export const MISSING_NODES_HEADER = 'X-EPIC-Nodes-Missing'
export const MISSING_BANDS_HEADER = 'X-EPIC-Bands-Missing'
// the time before which data are missing, or "true" when it is not known
export const ARCHIVE_MISSING_HEADER = 'X-EPIC-Archive-Missing'

const list = (v: string | null) => (v ?? '').split(',').map(s => s.trim()).filter(Boolean)

export function flagsFromHeaders(headers: Headers): NodeFlags {
  const archive = headers.get(ARCHIVE_MISSING_HEADER)
  return {
    nodes_missing: list(headers.get(MISSING_NODES_HEADER)),
    bands_missing: list(headers.get(MISSING_BANDS_HEADER)).map(Number).filter(Number.isFinite),
    archive_missing: !!archive,
    archive_before: archive && archive != 'true' ? archive : null
  }
}

export function anyMissing(flags?: NodeFlags | null): boolean {
  return !!flags?.nodes_missing?.length || !!flags?.archive_missing
}

// The note on a missing archive; its date is the UTC day of the boundary
function archiveNote(flags: NodeFlags): string {
  if (!flags.archive_missing) return ''
  const day = flags.archive_before ? String(flags.archive_before).slice(0, 10) : ''
  return day
    ? `Data older than ${day} are not available because the archive database did not respond.`
    : 'Older data are not available because the archive database did not respond.'
}

// Sentences saying which bands and which older data are missing, empty when
// nothing is
export function missingNote(flags?: NodeFlags | null): string {
  if (!anyMissing(flags)) return ''
  return [bandsNote(flags!), archiveNote(flags!)].filter(Boolean).join(' ')
}

// Bands are named by their lowest frequency, as in the session list
function bandsNote(flags: NodeFlags): string {
  if (!flags.nodes_missing?.length) return ''
  const mhz = [...new Set(flags!.bands_missing ?? [])].sort((a, b) => a - b)
    .map(c => (c * CHAN_BW_HZ / 1e6).toFixed(3))
  if (!mhz.length) return 'Some bands may be missing because an imaging node did not respond.'
  if (mhz.length == 1) return `The ${mhz[0]} MHz band is missing because its imaging node did not respond.`
  return `The ${mhz.slice(0, -1).join(', ')} and ${mhz[mhz.length - 1]} MHz bands are missing because their imaging nodes did not respond.`
}
