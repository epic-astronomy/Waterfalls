// How the pulsars the all-sky monitors know are named on the page. The Crab
// pulsar, the source of giant pulses at these frequencies, is shown as a crab.
export interface Pulsar {
  name: string, ra_deg: number, dec_deg: number, dm: number, period_s: number | null,
  alias?: string | null, giant_pulses?: boolean
}

// A crab drawn here rather than the emoji, which needs an emoji font the
// viewer may not have: body, eyes on stalks, two claws and three legs a side
const CRAB_HALF = `
  <path d="M5.4 10.7C3.3 10.5 2 8.7 2.6 6.9C3 5.8 4.4 5.3 5.3 6L4.3 7.6L6 7.9C6.3 8.9 6.1 10 5.4 10.7Z"/>
  <path d="M7 12.6L5.4 10.7M6.6 14.8L3.2 16.2M7.2 16.3L4.2 18.8M8.6 17.5L6.2 20.4M10.2 10.6L9.6 8.2" fill="none" stroke-width="1.3" stroke-linecap="round"/>
  <circle cx="9.5" cy="7.5" r="1.1"/>`
export const CRAB_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#f97316" stroke="#f97316">
  <ellipse cx="12" cy="14" rx="5.8" ry="4.1"/>
  <g>${CRAB_HALF}</g><g transform="translate(24 0) scale(-1 1)">${CRAB_HALF}</g>
  <circle cx="9.5" cy="7.3" r="0.45" fill="#1f2937" stroke="none"/><circle cx="14.5" cy="7.3" r="0.45" fill="#1f2937" stroke="none"/>
</svg>`
export const CRAB_DATA_URL = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(CRAB_SVG)}`

const ICONS: Record<string, string> = { 'B0531+21': 'crab' }

// the short label in text: the name, or nothing where an icon stands for it
export const pulsarLabel = (name: string) => ICONS[name] ? '' : name
// the full name, for titles and screen readers
export const pulsarTitle = (name: string, alias?: string | null) =>
  alias ? `${alias} pulsar (${name})` : `PSR ${name}`
export const hasIcon = (name: string) => name in ICONS
