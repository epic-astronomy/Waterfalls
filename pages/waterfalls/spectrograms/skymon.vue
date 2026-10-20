<script setup lang="ts">
// All-sky monitor: every imaging worker searches its own band of the whole
// visible sky for dispersed bursts. This page shows the state of each
// monitor, the candidates they found, and the spectrogram of any position.
import { radec2pix } from '~/lib/healpix'
import { hasIcon, pulsarLabel, type Pulsar } from '~/lib/pulsars'
const rtConfig = useRuntimeConfig()
const tz = useTimeZone()
const route = useRoute()
const router = useRouter()
// the lists, in tabs beside the viewer
const tabs = [{ label: 'FRBs', slot: 'frbs' }, { label: 'Pulsars', slot: 'pulsars' }]
const tab = ref(route.query.tab == 'pulsars' ? 1 : 0)
const frbView = ref<'candidates' | 'events'>(route.query.view == 'candidates' ? 'candidates' : 'events')

interface Node {
  node: string, up: boolean, error?: string,
  band?: { f_lo: number, f_hi: number, nchan: number, dt: number },
  tracked?: number, nside?: number, beam_deg?: number, lag_s?: number | null,
  cpu_fraction?: number | null, images?: number, missing_images?: number,
  candidates?: { stored: number, rfi: number, injection: number, duplicates: number },
  threshold?: number, pix_deg?: number, last_image_unix?: number | null,
  injections?: { injected: number, recovered: number, missed: number, active: number },
  tiers?: { dm_max: number }[],
  conditions?: { latest?: { disturbed: boolean, reasons: string[], noise_ratio: number | null } | null,
    summary?: { disturbed_since: number | null } | null },
  rfi_flagging?: { flagged_fraction_last_minute: number | null, masked_mhz: number[] }
}
interface Cand {
  id: string, node: string, cls: string, snr: number, dm: number, width_s: number, t_inf: number,
  utc_inf: string, ra: number, dec: number, el: number, tier: number, n_pix: number,
  f_lo_mhz: number, f_hi_mhz: number, injection_id?: string | null,
  known_source?: { kind: string, name: string, sep_deg: number, alias?: string | null, giant_pulse?: boolean } | null,
  flux?: { fluence_jy_ms: number, fluence_err_jy_ms: number | null } | null,
  rfi_reasons?: string[]
}

const nodes = ref<Node[]>([])
const nodesPending = ref(false)
const nodesLoaded = ref(false)
async function loadNodes() {
  nodesPending.value = true
  try { nodes.value = await $fetch<Node[]>(rtConfig.public.fastapiBase + '/skymon/nodes') }
  catch { nodes.value = [] }
  finally { nodesPending.value = false; nodesLoaded.value = true }
}

// events of the combiner: candidates checked in every band that could see them
interface BandState {
  state?: string, f_lo?: number, f_hi?: number, el_at_arrival?: number, predicted_t_bottom?: number,
  reason?: string, candidate?: { id?: string, snr: number, dm: number, fluence_jy_ms?: number | null },
  followup?: { snr: number, dm: number, fluence_jy_ms?: number | null }
}
interface Solar { type: string, cls?: string | null, begin: string, max?: string | null, end?: string | null }
interface Ev {
  id: string, kind: string, status: string, ra: number | null, dec: number | null, dm: number | null, dm_err: number | null,
  t_inf: number, combined_snr: number | null, best_snr?: number | null, seen?: string[], could_see?: string[],
  bands: Record<string, BandState & { data_id?: string }>,
  spectrum?: { plausible: boolean | null, consistent_with?: string[] },
  review?: string, reviews?: { verdict: string, by: string, note: string, at: number }[],
  other_dm?: { node: string, id: string, dm: number, snr: number }[],
  notes?: string[], disturbed?: boolean, reason?: string,
  candidates?: { node: string, id: string, dm: number, snr: number }[],
  context?: {
    sun_el_deg: number | null, sun_sep_deg: number | null, solar: Solar[] | null,
    lightning: { strikes_100km: number, nearest_km: number | null, complete: boolean } | null
  } | null
}
const events = ref<Ev[]>([])
const combinerUp = ref<boolean | null>(null)
const eventsPending = ref(true)
const showInjEvents = ref(false)
const showUnconfirmable = ref(true)
const showTerrestrial = ref(false)
async function loadEvents() {
  eventsPending.value = true
  try {
    const r = await $fetch<{ up: boolean, events: Ev[] }>(rtConfig.public.fastapiBase + '/skymon/events', { query: { since_h: sinceH.value } })
    combinerUp.value = r.up
    events.value = r.events
  } catch { combinerUp.value = false; events.value = [] }
  finally { eventsPending.value = false }
}
const shownEvents = computed(() => events.value.filter(e =>
  (showInjEvents.value || e.kind != 'injection') && (showUnconfirmable.value || e.status != 'unconfirmable') &&
  (showTerrestrial.value || e.kind != 'terrestrial') &&
  (showReviewed.value || e.review == 'pending' || e.kind == 'terrestrial')))
const evLabel: Record<string, string> = {
  pending: 'Pending', confirmed: 'Confirmed', band_limited: 'One band, plausible spectrum',
  implausible: 'One band, implausible spectrum', unconfirmable: 'Not checkable', single_band: 'One band',
  terrestrial: 'Terrestrial, in several bands at once'
}
const evColor: Record<string, string> = {
  pending: 'sky', confirmed: 'green', band_limited: 'amber', implausible: 'gray', unconfirmable: 'gray', single_band: 'amber', terrestrial: 'gray'
}
const reviewLabel: Record<string, string> = { pending: 'To review', frb: 'FRB', rfi: 'RFI', unclear: 'Unclear', 'not needed': '' }
const showReviewed = ref(true)

// review verdicts, for logged-in users; the server checks the session with Hanko
const hanko = useHanko()
const canReview = ref(false)
const reviewNote = ref('')
const reviewMsg = ref('')
async function submitReview(e: Ev, verdict: string) {
  reviewMsg.value = ''
  try {
    const r = await $fetch<{ review: string, reviews: Ev['reviews'] }>(
      rtConfig.public.fastapiBase + `/skymon/events/${encodeURIComponent(e.id)}/review`,
      { method: 'POST', body: { verdict, note: reviewNote.value } })
    e.review = r.review
    e.reviews = r.reviews
    reviewNote.value = ''
    reviewMsg.value = 'Saved.'
  } catch (err: any) {
    reviewMsg.value = err?.data?.detail ?? 'The review could not be saved.'
  }
}
const bandLabel: Record<string, string> = {
  detected: 'detected', followup: 'measured', watching: 'watching', not_visible: 'not visible',
  node_down: 'not answering', searched: 'searched'
}
function solarText(r: Solar) {
  const t = (iso?: string | null) => iso ? tz.dateTime(Date.parse(iso)) : ''
  const kind = r.type == 'XRA' ? `X-ray flare${r.cls ? ' ' + r.cls : ''}` : `radio burst${r.cls ? ' type ' + r.cls : ''}`
  return `${kind}, ${t(r.begin)}${r.end ? ' to ' + t(r.end) : ''}`
}
function showEvent(e: Ev) {
  if (e.ra == null || e.dec == null || e.dm == null) return
  // the data kept by the band that detected it, else the live pixel with the burst's track
  const dataId = (b?: BandState & { data_id?: string }) => b?.candidate?.id ?? b?.data_id
  const n = Object.keys(e.bands ?? {}).find(b => e.bands[b].state == 'detected' && dataId(e.bands[b]))
    ?? Object.keys(e.bands ?? {}).find(b => dataId(e.bands[b])) ?? node.value
  showCandidate({ node: n, id: n ? dataId(e.bands[n]) : undefined, ra: e.ra, dec: e.dec, t_inf: e.t_inf, dm: e.dm } as Cand)
}
const expanded = ref<string | null>(null)

const sinceH = ref(Number(route.query.since_h) || 24)
const showInjections = ref(route.query.inj == '1')
const showRfi = ref(false)
const showKnown = ref(false)
const cands = ref<Cand[]>([])
const candsPending = ref(true)
async function loadCands() {
  candsPending.value = true
  try { cands.value = await $fetch<Cand[]>(rtConfig.public.fastapiBase + '/skymon/candidates', { query: { since_h: sinceH.value } }) }
  catch { cands.value = [] }
  finally { candsPending.value = false }
}
const shownCands = computed(() => cands.value.filter(c =>
  (c.cls == 'candidate') || (showInjections.value && c.cls == 'injection') || (showRfi.value && c.cls == 'rfi') || (showKnown.value && c.cls == 'known')))

const sinceOptions = [{ label: '6 hours', value: 6 }, { label: '24 hours', value: 24 }, { label: '3 days', value: 72 }, { label: '7 days', value: 168 }]

// the monitor whose sky and spectrograms are shown, and the pixel picked on its
// sky, both in the address so a view can be shared
const node = ref<string | null>(typeof route.query.node == 'string' ? route.query.node : null)
const selNode = computed(() => nodes.value.find(n => n.node == node.value) ?? null)
watch(nodes, ns => {
  if (!node.value || !ns.some(n => n.node == node.value)) node.value = ns.find(n => n.up && n.band)?.node ?? ns[0]?.node ?? null
})
const ra = ref(route.query.ra != null ? Number(route.query.ra) : null as number | null)
const dec = ref(route.query.dec != null ? Number(route.query.dec) : null as number | null)
const pickedHpix = ref<number | null>(null)
const mapNside = ref<number | null>(null)
const selectedHpix = computed(() => {
  if (pickedHpix.value != null) return pickedHpix.value
  return ra.value != null && dec.value != null && mapNside.value ? radec2pix(mapNside.value, ra.value, dec.value) : null
})
const mark = ref<{ tInf: number, dm: number } | null>(null)
// a candidate whose kept data are shown instead of the live pixel
const openCand = ref<{ node: string, id: string } | null>(typeof route.query.cand == 'string' && route.query.cand.includes(':')
  ? { node: route.query.cand.split(':')[0], id: route.query.cand.split(':').slice(1).join(':') } : null)
const skyMap = ref<{ centreOn: (ra: number, dec: number) => void } | null>(null)
function setPosition(r: number, d: number, hpix: number | null = null) {
  ra.value = r
  dec.value = d
  pickedHpix.value = hpix
}
// the candidate of the position shown, kept while its pixel is viewed live, so the
// viewer can switch back to its burst
const lastCand = ref<{ node: string, id: string } | null>(openCand.value)
function onPick(p: { hpix: number, nside: number, ra: number, dec: number }) {
  setPosition(p.ra, p.dec, p.hpix)
  mark.value = null
  openCand.value = null
  lastCand.value = null
}
// what the viewer shows of the position: the burst's kept data, the live search
// window, or the 10 s averages (shared with SkymonSpectrogram)
const resolution = useState<'live' | 'avg'>('skymon-spec-resolution', () => 'live')
const specHours = useState('skymon-spec-hours', () => 1)
const viewMode = computed(() => openCand.value ? 'burst' : resolution.value)
function setView(m: string) {
  if (m == 'burst') { if (lastCand.value) openCand.value = lastCand.value; return }
  openCand.value = null
  resolution.value = m as 'live' | 'avg'
}
const viewModes = computed(() => [
  ...(lastCand.value ? [{ value: 'burst', label: 'Burst' }] : []),
  { value: 'live', label: `Live, ${((selNode.value?.band?.dt ?? 0.0836) * 1000).toFixed(1)} ms` },
  { value: 'avg', label: '10 s averages' }
])
function selectNode(n: string) {
  if (n == node.value) return
  node.value = n
  pickedHpix.value = null  // the pixel of this position on the new monitor's grid
}
function showCandidate(c: Cand) {
  if (!c.id) {  // a tallied pulse, without data: the 10 s averages at its position, its arrival marked
    if (c.node) selectNode(c.node)
    setPosition(c.ra, c.dec)
    mark.value = { tInf: c.t_inf, dm: c.dm }
    openCand.value = null
    lastCand.value = null
    resolution.value = 'avg'
    skyMap.value?.centreOn(c.ra, c.dec)
    return
  }
  if (c.node) selectNode(c.node)
  setPosition(c.ra, c.dec)
  mark.value = { tInf: c.t_inf, dm: c.dm }
  openCand.value = c.node && c.id ? { node: c.node, id: c.id } : null
  lastCand.value = openCand.value
  skyMap.value?.centreOn(c.ra, c.dec)
}
watch([node, ra, dec, sinceH, showInjections, openCand, () => tab.value, () => frbView.value], () => {
  const q: Record<string, string> = {}
  if (node.value) q.node = node.value
  if (openCand.value) q.cand = `${openCand.value.node}:${openCand.value.id}`
  if (tab.value == 1) q.tab = 'pulsars'
  if (frbView.value == 'candidates') q.view = 'candidates'
  if (ra.value != null && dec.value != null) { q.ra = ra.value.toFixed(4); q.dec = dec.value.toFixed(4) }
  if (sinceH.value != 24) q.since_h = String(sinceH.value)
  if (showInjections.value) q.inj = '1'
  router.replace({ query: q })
})
// candidates of the shown monitor, marked on its sky
const markers = computed(() => cands.value
  .filter(c => c.node == node.value && (c.cls == 'candidate' || (showInjections.value && c.cls == 'injection')))
  .map(c => ({ ra: c.ra, dec: c.dec, color: c.cls == 'injection' ? '#38bdf8' : '#f59e0b', title: `S/N ${c.snr.toFixed(1)}, DM ${c.dm.toFixed(1)}` })))
// what a viewer knows a monitor by: the band it observes, by its centre frequency
const bandNames = computed(() => Object.fromEntries(nodes.value.filter(n => n.band)
  .map(n => [n.node, `${((n.band!.f_lo + n.band!.f_hi) / 2).toFixed(1)} MHz`])) as Record<string, string>)
const bandName = (node?: string | null) => (node && bandNames.value[node]) || ''
const candCount = (n: Node) => n.candidates ? n.candidates.stored - n.candidates.rfi - n.candidates.injection : null
const dmReach = (n: Node) => n.tiers?.length ? Math.round(n.tiers[n.tiers.length - 1].dm_max) : null
watch(sinceH, () => { loadCands(); loadEvents() })

const fmt = (x?: number | null, d = 1) => x == null ? '' : x.toFixed(d)
const clsLabel: Record<string, string> = { candidate: 'Candidate', injection: 'Test injection', rfi: 'RFI', known: 'Known source' }
const clsColor: Record<string, string> = { candidate: 'amber', injection: 'sky', rfi: 'gray', known: 'violet' }
const knownLabel: Record<string, string> = { solar: 'Sun', jovian: 'Jupiter', bright_source: '', pulsar: 'pulsar' }
function clsText(c: Cand) {
  if (c.cls == 'known' && c.known_source?.kind == 'pulsar') {
    const ks = c.known_source
    return hasIcon(ks.name) ? '' : 'single pulse'  // after the pulsar's name (SkymonPulsarName); the crab says it all
  }
  if (c.cls == 'known' && c.known_source) {
    const k = knownLabel[c.known_source.kind]
    return k && k != c.known_source.name ? `${c.known_source.name} (${k})` : c.known_source.name
  }
  if (c.cls == 'rfi' && c.rfi_reasons?.length) return c.rfi_reasons.join(', ')
  return ''
}
const reasonLabel: Record<string, string> = { noise: 'high noise', rfi_rate: 'frequent RFI', sky_triggered: 'much of the sky triggered' }

// pulsars: the list the monitors use, and their single pulses (class known) in the period
const pulsars = ref<Pulsar[]>([])
const pulses = ref<Cand[]>([])
const pulsesPending = ref(true)
async function loadPulsars() {
  try { if (!pulsars.value.length) pulsars.value = await $fetch<Pulsar[]>(rtConfig.public.fastapiBase + '/skymon/pulsars') }
  catch { pulsars.value = [] }
  try {
    // giant pulses are stored (with data); the single pulses of ordinary pulsars are only
    // tallied by the monitors, for the last 24 h (without data: they open the averages)
    const [known, tally] = await Promise.all([
      $fetch<Cand[]>(rtConfig.public.fastapiBase + '/skymon/candidates', { query: { since_h: sinceH.value, cls: 'known', limit: 5000 } }),
      $fetch<Record<string, [number, number, number, string][]>>(rtConfig.public.fastapiBase + '/skymon/pulsars/pulses').catch(() => ({}))
    ])
    const since = Date.now() / 1000 - sinceH.value * 3600
    const tallied: Cand[] = []
    for (const [name, ps] of Object.entries(tally)) {
      const p = pulsars.value.find(x => x.name == name)
      if (!p) continue
      for (const [t, snr, dm, node] of ps) if (t >= since)
        tallied.push({ id: '', node, cls: 'known', snr, dm, t_inf: t, ra: p.ra_deg, dec: p.dec_deg,
          known_source: { kind: 'pulsar', name, sep_deg: 0 } } as Cand)
    }
    pulses.value = [...known.filter(c => c.known_source?.kind == 'pulsar'), ...tallied]
  } catch { pulses.value = [] }
  finally { pulsesPending.value = false }
}
const pulsarRows = computed(() => pulsars.value.map(p => {
  const mine = pulses.value.filter(c => c.known_source?.name == p.name).sort((a, b) => b.t_inf - a.t_inf)
  const brightest = mine.reduce<Cand | null>((a, c) => !a || c.snr > a.snr ? c : a, null)
  const last = mine.reduce<Cand | null>((a, c) => !a || c.t_inf > a.t_inf ? c : a, null)
  return { p, n: mine.length, brightest, last, pulses: mine }
}).sort((a, b) => b.n - a.n || Number(!!b.p.giant_pulses) - Number(!!a.p.giant_pulses) || a.p.name.localeCompare(b.p.name)))
const showQuietPulsars = ref(false)
const shownPulsarRows = computed(() => pulsarRows.value.filter(r => r.n || showQuietPulsars.value))
const openPulsar = ref<string | null>(null)
const mapPulsars = computed(() => pulsars.value.map(p => ({ ra: p.ra_deg, dec: p.dec_deg, label: pulsarLabel(p.name), icon: hasIcon(p.name),
  active: pulses.value.some(c => c.known_source?.name == p.name) })))
watch(sinceH, loadPulsars)

// pulsars with pulses among the candidates shown: their DMs are marked on the DM-time overview
const dmtPulsars = computed(() => {
  const names = new Set(shownCands.value.filter(c => c.known_source?.kind == 'pulsar').map(c => c.known_source!.name))
  return pulsars.value.filter(p => names.has(p.name)).map(p => ({ name: p.name, label: p.alias ?? p.name, dm: p.dm }))
})
// up and down (or j and k) step through the list into the viewer
function onKey(e: KeyboardEvent) {
  if (e.target instanceof HTMLElement && e.target.closest('input, textarea, select, [contenteditable="true"]')) return
  const step = e.key == 'ArrowDown' || e.key == 'j' ? 1 : e.key == 'ArrowUp' || e.key == 'k' ? -1 : 0
  if (!step) return
  const list = tab.value == 1 ? (pulsarRows.value.find(r => r.p.name == openPulsar.value)?.pulses ?? []) : shownCands.value
  if (!list.length || (tab.value == 0 && frbView.value != 'candidates')) return
  const i = list.findIndex(c => isOpen(c))
  const next = list[i < 0 ? 0 : Math.min(list.length - 1, Math.max(0, i + step))]
  if (!next || (i >= 0 && list[i] === next)) return
  e.preventDefault()
  showCandidate(next)
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
// how many of the FRB list's optional groups are included (the count on its menu)
const frbIncludeCount = computed(() => frbView.value == 'candidates'
  ? [showInjections.value, showRfi.value, showKnown.value].filter(Boolean).length
  : [showInjEvents.value, showUnconfirmable.value, showReviewed.value, showTerrestrial.value].filter(Boolean).length)
// the viewer's title for an open candidate: what it is and when it arrived, by its
// arrival at infinite frequency (the class itself is in the badge below)
const viewerTitle = computed(() => {
  const o = openCand.value
  const c = o && [...cands.value, ...pulses.value].find(x => x.node == o.node && x.id == o.id)
  if (!c) return 'Burst'
  const what = c.cls == 'known' && c.known_source?.kind == 'pulsar' ? 'Pulse' : c.cls == 'rfi' ? 'Signal' : 'Burst'
  return `${what} at ${tz.clock(c.t_inf * 1000)} ${tz.zoneName(c.t_inf * 1000)}`
})
const isOpen = (c: Cand) => openCand.value?.node == c.node && openCand.value?.id == c.id
// an event's bands, lowest frequency first: what each found or measured, and its data if kept
function eventBands(e: Ev) {
  return Object.entries(e.bands ?? {}).map(([n, b]) => {
    const m = b.candidate ?? b.followup
    const id = b.candidate?.id ?? b.data_id
    const nd = nodes.value.find(x => x.node == n)
    return { node: n, state: b.state ?? '', snr: m?.snr ?? null, dm: m?.dm ?? null, id: id ?? null,
      f: nd?.band ? (nd.band.f_lo + nd.band.f_hi) / 2 : b.f_lo ?? 1e9 }
  }).sort((a, b) => a.f - b.f)
}
function openBand(e: Ev, b: { node: string, id: string | null }) {
  if (!b.id || e.ra == null || e.dec == null || e.dm == null) return
  showCandidate({ node: b.node, id: b.id, ra: e.ra, dec: e.dec, t_inf: e.t_inf, dm: e.dm } as Cand)
}
function openEvent(e: Ev) {
  expanded.value = expanded.value == e.id ? null : e.id
  if (expanded.value) showEvent(e)
}
// on narrow screens the viewer is below the lists: bring it into view
const viewer = ref<HTMLElement>()
watch(openCand, c => {
  if (c && import.meta.client && window.innerWidth < 1280) nextTick(() => viewer.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
})

// refreshed every minute while the page is open (in the browser only)
let timer: ReturnType<typeof setInterval> | undefined
let nodeTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  tz.restore()
  try { canReview.value = !!hanko?.session.isValid() } catch { canReview.value = false }
  loadNodes()
  loadCands()
  loadEvents()
  loadPulsars()
  // the lists every 15 s, so a burst seen in a spectrogram is soon in them; the bands every minute
  timer = setInterval(() => { loadCands(); loadEvents(); loadPulsars() }, 15000)
  nodeTimer = setInterval(loadNodes, 60000)
})
onBeforeUnmount(() => { clearInterval(timer); clearInterval(nodeTimer) })

useSeoMeta({
  title: 'All-sky monitor @ LWA-Sevilleta',
  ogTitle: 'All-sky monitor @ LWA-Sevilleta',
  description: 'Real-time search of the whole sky visible from the Long Wavelength Array station in Sevilleta for dispersed radio bursts, with the EPIC imager.',
  ogDescription: 'Real-time search of the whole sky visible from the Long Wavelength Array station in Sevilleta for dispersed radio bursts, with the EPIC imager.'
})
</script>

<template>
  <PageToolbar>
    <span class="text-sm text-gray-500 dark:text-gray-400">All-sky monitor</span>
    <div class="flex items-center gap-2 text-sm">
      <span class="text-gray-500 dark:text-gray-400">Period</span>
      <USelect v-model="sinceH" :options="sinceOptions" size="xs" />
    </div>
    <template #right><TimeZoneToggle /></template>
  </PageToolbar>
  <UDashboardPanelContent>
    <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-3 items-start">
      <!-- left: the sky, the monitors, and the lists -->
      <div class="space-y-3 min-w-0">
        <UCard :ui="{ body: { padding: 'p-2 sm:p-3' }, header: { padding: 'px-3 py-2 sm:px-4' } }">
          <template #header>
            <div class="flex items-center gap-2">
              <span class="font-medium">Sky</span>
              <span v-if="selNode?.band" class="text-sm text-gray-500 dark:text-gray-400">
                {{ selNode.band.f_lo.toFixed(2) }}–{{ selNode.band.f_hi.toFixed(2) }} MHz, last 5 min
              </span>
            </div>
          </template>
          <SpectrogramSkymonSkyMap ref="skyMap" :node="node" :waiting="!nodesLoaded" :selected="selectedHpix" :markers="markers" :pulsars="mapPulsars"
            @select="onPick" @nside="n => mapNside = n" />
        </UCard>

        <UCard :ui="{ body: { padding: 'p-1 sm:p-2' }, header: { padding: 'px-3 py-2 sm:px-4' } }">
          <template #header>
            <div class="flex items-center gap-2">
              <span class="font-medium">Bands</span>
              <div class="flex-1" />
              <UButton size="xs" variant="ghost" icon="i-heroicons-arrow-path" :loading="nodesPending" aria-label="Reload the monitors" @click="loadNodes" />
            </div>
          </template>
          <SpectrogramSkymonLoading v-if="!nodesLoaded" compact :messages="[
            'Asking the six monitors for their state',
            'Collecting bands, tracked pixels and candidates',
            'Waiting for the slower monitors to answer']" />
          <div v-else class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead class="text-left text-gray-500 dark:text-gray-400">
                <tr>
                  <th class="px-2 py-1">Band (MHz)</th><th class="px-2 py-1">State</th>
                  <th class="px-2 py-1 text-right">Pixels</th><th class="px-2 py-1 text-right">DM reach</th>
                  <th class="px-2 py-1 text-right">Candidates</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="n in nodes" :key="n.node" class="border-t border-gray-200 dark:border-gray-800 cursor-pointer"
                  :class="n.node == node ? 'bg-primary-50 dark:bg-primary-950/40' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'"
                  @click="selectNode(n.node)">
                  <td class="px-2 py-1 tabular-nums whitespace-nowrap">{{ n.band ? `${n.band.f_lo.toFixed(2)}–${n.band.f_hi.toFixed(2)}` : '' }}</td>
                  <td class="px-2 py-1">
                    <UBadge :color="!n.up ? 'red' : n.conditions?.latest?.disturbed ? 'orange' : 'green'" variant="subtle" size="xs"
                      :label="!n.up ? 'Not answering' : n.conditions?.latest?.disturbed ? 'Disturbed' : 'Running'" />
                  </td>
                  <td class="px-2 py-1 text-right tabular-nums">{{ n.tracked ?? '' }}</td>
                  <td class="px-2 py-1 text-right tabular-nums" :title="dmReach(n) != null ? 'pc cm⁻³' : undefined">{{ dmReach(n) ?? '' }}</td>
                  <td class="px-2 py-1 text-right tabular-nums">{{ candCount(n) ?? '' }}</td>
                </tr>
                <tr v-if="!nodes.length && !nodesPending"><td colspan="5" class="px-2 py-3 text-center text-gray-500">No monitor answered.</td></tr>
              </tbody>
            </table>
          </div>
        </UCard>

        <UCard :ui="{ body: { padding: 'p-1 sm:p-2' } }">
          <UTabs v-model="tab" :items="tabs" :ui="{ list: { width: 'w-full' } }">
            <template #frbs>
              <div class="flex flex-wrap items-center gap-x-4 gap-y-2 px-1 py-2 text-sm">
                <USelect v-model="frbView" size="xs" :options="[{ value: 'events', label: 'FRBs (events)' }, { value: 'candidates', label: 'All candidates' }]" />
                <!-- what the list includes, as a checklist in a menu -->
                <UPopover>
                  <UButton size="xs" color="gray" variant="outline" trailing-icon="i-heroicons-chevron-down-20-solid"
                    :label="`Include (${frbIncludeCount})`" />
                  <template #panel>
                    <div class="p-3 space-y-2 text-sm">
                      <template v-if="frbView == 'candidates'">
                        <UCheckbox v-model="showInjections" label="Test injections" />
                        <UCheckbox v-model="showRfi" label="RFI" />
                        <UCheckbox v-model="showKnown" label="Known sources" />
                      </template>
                      <template v-else>
                        <UCheckbox v-model="showInjEvents" label="Test injections" />
                        <UCheckbox v-model="showUnconfirmable" label="Single band only" />
                        <UCheckbox v-model="showReviewed" label="Already reviewed" />
                        <UCheckbox v-model="showTerrestrial" label="Terrestrial" />
                      </template>
                    </div>
                  </template>
                </UPopover>
                <UBadge v-if="frbView == 'events' && combinerUp === false" color="red" variant="subtle" size="xs" label="Combiner not answering" />
                <div class="flex-1" />
                <UButton size="xs" variant="ghost" icon="i-heroicons-arrow-path" :loading="frbView == 'events' ? eventsPending : candsPending"
                  aria-label="Reload" @click="frbView == 'events' ? loadEvents() : loadCands()" />
              </div>
              <!-- every candidate of the period, whichever list is shown below -->
                <SpectrogramSkymonDmTime :cands="shownCands" :pulsars="dmtPulsars" :open="openCand" :bands="bandNames" @select="showCandidate" />
              <!-- candidates of all monitors -->
              <template v-if="frbView == 'candidates'">
                <div class="overflow-auto max-h-[32rem]">
                  <table class="min-w-full text-sm">
                    <thead class="text-left text-gray-500 dark:text-gray-400 sticky top-0 bg-white dark:bg-gray-900 z-10">
                      <tr>
                        <th class="px-2 py-1">Arrival ({{ tz.zoneName() }})</th><th class="px-2 py-1">Band</th>
                        <th class="px-2 py-1 text-right">S/N</th><th class="px-2 py-1 text-right">DM</th><th class="px-2 py-1">Class</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="c in shownCands" :key="c.node + c.id" class="border-t border-gray-200 dark:border-gray-800 cursor-pointer"
                        :class="isOpen(c) ? 'bg-primary-50 dark:bg-primary-950/40' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'"
                        :title="`RA ${c.ra.toFixed(2)}°, Dec ${c.dec.toFixed(2)}°, elevation ${c.el.toFixed(0)}°, width ${c.width_s.toFixed(2)} s`"
                        @click="showCandidate(c)">
                        <td class="px-2 py-1 font-mono whitespace-nowrap">{{ tz.dateTime(c.t_inf * 1000) }}</td>
                        <td class="px-2 py-1 whitespace-nowrap">{{ bandName(c.node) }}</td>
                        <td class="px-2 py-1 text-right tabular-nums">{{ c.snr.toFixed(1) }}</td>
                        <td class="px-2 py-1 text-right tabular-nums">{{ c.dm.toFixed(1) }}</td>
                        <td class="px-2 py-1">
                          <UBadge :color="clsColor[c.cls]" variant="subtle" size="xs" :label="clsLabel[c.cls] ?? c.cls" />
                          <SpectrogramSkymonPulsarName v-if="c.cls == 'known' && c.known_source?.kind == 'pulsar'" class="ml-1 text-xs"
                            :name="c.known_source.name" :alias="c.known_source.alias" :size="18" />
                          <span v-if="clsText(c)" class="ml-1 text-xs text-gray-500 dark:text-gray-400">{{ clsText(c) }}</span>
                        </td>
                      </tr>
                      <tr v-if="!shownCands.length && candsPending"><td colspan="5">
                        <SpectrogramSkymonLoading compact :messages="['Asking every monitor for its candidates', 'Merging the candidates of all bands']" /></td></tr>
                      <tr v-if="!shownCands.length && !candsPending"><td colspan="5" class="px-2 py-3 text-center text-gray-500">No candidates in this period.</td></tr>
                    </tbody>
                  </table>
                </div>
              </template>
              <!-- events of the combiner -->
              <template v-else>
                <div class="overflow-auto max-h-[32rem]">
                  <table class="min-w-full text-sm">
                    <thead class="text-left text-gray-500 dark:text-gray-400 sticky top-0 bg-white dark:bg-gray-900 z-10">
                      <tr>
                        <th class="px-2 py-1">Arrival ({{ tz.zoneName() }})</th><th class="px-2 py-1">Result</th>
                        <th class="px-2 py-1 text-right">DM</th><th class="px-2 py-1 text-right">S/N</th><th class="px-2 py-1">Bands</th>
                      </tr>
                    </thead>
                    <tbody>
                      <template v-for="e in shownEvents" :key="e.id">
                        <tr class="border-t border-gray-200 dark:border-gray-800 cursor-pointer"
                          :class="expanded == e.id ? 'bg-primary-50 dark:bg-primary-950/40' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'"
                          @click="openEvent(e)">
                          <td class="px-2 py-1 font-mono whitespace-nowrap">
                            <UIcon :name="expanded == e.id ? 'i-heroicons-chevron-down-20-solid' : 'i-heroicons-chevron-right-20-solid'" class="w-4 h-4 align-middle text-gray-400" />
                            {{ tz.dateTime(e.t_inf * 1000) }}
                          </td>
                          <td class="px-2 py-1 whitespace-nowrap">
                            <UBadge :color="evColor[e.status]" variant="subtle" size="xs" :label="evLabel[e.status] ?? e.status" />
                            <UBadge v-if="e.kind == 'injection'" color="sky" variant="outline" size="xs" label="Test injection" class="ml-1" />
                            <UBadge v-if="reviewLabel[e.review ?? '']" :color="e.review == 'pending' ? 'orange' : 'gray'" variant="outline" size="xs"
                              :label="reviewLabel[e.review ?? '']" class="ml-1" />
                            <UBadge v-if="e.disturbed" color="orange" variant="outline" size="xs" label="Band disturbed" class="ml-1" />
                            <UBadge v-if="e.other_dm?.length" color="violet" variant="outline" size="xs" label="Other DMs here" class="ml-1" />
                          </td>
                          <td class="px-2 py-1 text-right tabular-nums whitespace-nowrap">{{ e.dm != null ? `${e.dm.toFixed(1)} ± ${(e.dm_err ?? 0).toFixed(1)}` : '' }}</td>
                          <td class="px-2 py-1 text-right tabular-nums">{{ e.combined_snr != null ? e.combined_snr.toFixed(1) : '' }}</td>
                          <td class="px-2 py-1 whitespace-nowrap">{{ e.kind == 'terrestrial' ? `${e.candidates?.length ?? 0} candidates` : e.seen?.length ? `${e.seen.length} of ${e.could_see?.length ?? 0}` : '' }}</td>
                        </tr>
                        <template v-if="expanded == e.id">
                          <tr v-for="b in eventBands(e)" :key="b.node" class="text-xs"
                            :class="[b.id ? 'cursor-pointer' : '', isOpen({ node: b.node, id: b.id ?? '' } as Cand) ? 'bg-primary-50 dark:bg-primary-950/40' : 'bg-gray-50 dark:bg-gray-800/40 hover:bg-gray-100 dark:hover:bg-gray-800']"
                            @click="openBand(e, b)">
                            <td class="pl-8 pr-2 py-1 whitespace-nowrap">{{ bandName(b.node) }}</td>
                            <td class="px-2 py-1">
                              <UBadge size="xs" variant="soft" :label="bandLabel[b.state] ?? b.state"
                                :color="b.state == 'detected' || (b.state == 'followup' && (b.snr ?? 0) >= 6) ? 'green' : b.state == 'watching' ? 'sky' : 'gray'" />
                            </td>
                            <td class="px-2 py-1 text-right tabular-nums">{{ b.dm != null ? b.dm.toFixed(1) : '' }}</td>
                            <td class="px-2 py-1 text-right tabular-nums">{{ b.snr != null ? b.snr.toFixed(1) : '' }}</td>
                            <td class="px-2 py-1 text-gray-500 dark:text-gray-400">{{ b.id ? 'open' : '' }}</td>
                          </tr>
                        </template>
                        <tr v-if="expanded == e.id" class="bg-gray-50 dark:bg-gray-800/50">
                          <td colspan="5" class="px-3 py-2 space-y-2">
                            <div class="text-xs text-gray-600 dark:text-gray-300">RA {{ fmt(e.ra, 2) }}°, Dec {{ fmt(e.dec, 2) }}°</div>
                            <p v-if="e.spectrum?.consistent_with?.length" class="text-xs text-gray-600 dark:text-gray-300">
                              The S/N measured in the bands is consistent with {{ e.spectrum.consistent_with.join(', or with ') }}.
                            </p>
                            <p v-if="e.kind == 'terrestrial'" class="text-xs text-gray-600 dark:text-gray-300">
                              {{ e.reason }}<template v-if="e.candidates?.length">. Candidates
                                {{ e.candidates.map(c => `${bandName(c.node)} S/N ${c.snr.toFixed(1)} at DM ${c.dm.toFixed(1)}`).join(', ') }}.</template>
                            </p>
                            <p v-if="e.other_dm?.length" class="text-xs text-gray-600 dark:text-gray-300">
                              Also found at this position during the sweep, at other DMs, with data kept
                              {{ e.other_dm.map(o => `${bandName(o.node)} S/N ${o.snr.toFixed(1)} at DM ${o.dm.toFixed(1)}`).join(', ') }}.
                              Each is the same burst at a neighbouring trial DM, or a second burst.
                            </p>
                            <div v-if="e.context" class="text-xs text-gray-600 dark:text-gray-300 space-y-0.5">
                              <div v-if="e.context.sun_el_deg != null">
                                Sun at elevation {{ e.context.sun_el_deg.toFixed(0) }}°, {{ fmt(e.context.sun_sep_deg, 0) }}° from the position.
                              </div>
                              <div v-for="(r, i) in e.context.solar ?? []" :key="i">Solar {{ solarText(r) }}.</div>
                              <div v-if="e.context.solar && !e.context.solar.length">No solar radio burst or flare reported near the arrivals.</div>
                              <div v-if="e.context.lightning">
                                {{ e.context.lightning.strikes_100km }} lightning strikes within 100 km<template v-if="e.context.lightning.nearest_km != null">, nearest {{ e.context.lightning.nearest_km.toFixed(0) }} km</template><template v-if="!e.context.lightning.complete"> (data incomplete)</template>.
                              </div>
                            </div>
                            <div v-if="e.notes?.length" class="text-xs text-gray-500 dark:text-gray-400">
                              <div v-for="(n, i) in e.notes" :key="i">{{ n }}</div>
                            </div>
                            <div v-if="e.reviews?.length" class="text-xs text-gray-600 dark:text-gray-300">
                              <div v-for="(r, i) in e.reviews" :key="i">
                                {{ tz.dateTime(r.at * 1000) }}, {{ r.by }} reviewed it as {{ reviewLabel[r.verdict] }}<template v-if="r.note">. {{ r.note }}</template>
                              </div>
                            </div>
                            <div v-if="e.kind == 'sky' && e.status != 'pending'" class="flex flex-wrap items-center gap-2">
                              <template v-if="canReview">
                                <UInput v-model="reviewNote" size="xs" placeholder="Note (optional)" class="w-60" @click.stop />
                                <UButton size="2xs" color="green" variant="soft" label="FRB" @click.stop="submitReview(e, 'frb')" />
                                <UButton size="2xs" color="red" variant="soft" label="RFI" @click.stop="submitReview(e, 'rfi')" />
                                <UButton size="2xs" color="gray" variant="soft" label="Unclear" @click.stop="submitReview(e, 'unclear')" />
                                <span v-if="reviewMsg" class="text-xs text-gray-500">{{ reviewMsg }}</span>
                              </template>
                              <span v-else class="text-xs text-gray-500">Log in to review this event.</span>
                            </div>
                          </td>
                        </tr>
                      </template>
                      <tr v-if="!shownEvents.length && eventsPending"><td colspan="5">
                        <SpectrogramSkymonLoading compact :messages="['Asking the combiner for the events', 'Collecting the bands of each event']" /></td></tr>
                      <tr v-if="!shownEvents.length && !eventsPending"><td colspan="5" class="px-2 py-3 text-center text-gray-500">No events in this period.</td></tr>
                    </tbody>
                  </table>
                </div>
              </template>
            </template>

            <template #pulsars>
              <div class="flex flex-wrap items-center gap-4 px-1 py-2 text-sm">
                <div class="flex-1" />
                <UCheckbox v-model="showQuietPulsars" label="Pulsars without pulses" />
              </div>
              <SpectrogramSkymonLoading v-if="pulsesPending" compact :messages="['Asking the monitors for their pulsars', 'Collecting the single pulses of each']" />
              <div v-else class="overflow-auto max-h-[32rem]">
                <table class="min-w-full text-sm">
                  <thead class="text-left text-gray-500 dark:text-gray-400 sticky top-0 bg-white dark:bg-gray-900 z-10">
                    <tr>
                      <th class="px-2 py-1">Pulsar</th><th class="px-2 py-1 text-right">DM</th><th class="px-2 py-1 text-right">Period (s)</th>
                      <th class="px-2 py-1 text-right">Pulses</th><th class="px-2 py-1 text-right">Brightest</th>
                      <th class="px-2 py-1">Last ({{ tz.zoneName() }})</th>
                    </tr>
                  </thead>
                  <tbody>
                    <template v-for="r in shownPulsarRows" :key="r.p.name">
                      <tr class="border-t border-gray-200 dark:border-gray-800" :class="r.n ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50' : 'text-gray-500 dark:text-gray-400'"
                        @click="r.n && (openPulsar = openPulsar == r.p.name ? null : r.p.name)">
                        <td class="px-2 py-1 whitespace-nowrap">
                          <UIcon v-if="r.n" :name="openPulsar == r.p.name ? 'i-heroicons-chevron-down-20-solid' : 'i-heroicons-chevron-right-20-solid'" class="w-4 h-4 align-middle text-gray-400" />
                          <SpectrogramSkymonPulsarName :name="r.p.name" :alias="r.p.alias" :size="24" />
                        </td>
                        <td class="px-2 py-1 text-right tabular-nums">{{ r.p.dm.toFixed(2) }}</td>
                        <td class="px-2 py-1 text-right tabular-nums">{{ r.p.period_s != null ? r.p.period_s.toFixed(4) : '' }}</td>
                        <td class="px-2 py-1 text-right tabular-nums">{{ r.n || '' }}</td>
                        <td class="px-2 py-1 text-right tabular-nums">{{ r.brightest ? r.brightest.snr.toFixed(1) : '' }}</td>
                        <td class="px-2 py-1 font-mono whitespace-nowrap">{{ r.last ? tz.dateTime(r.last.t_inf * 1000) : '' }}</td>
                      </tr>
                      <template v-if="openPulsar == r.p.name">
                        <tr v-for="c in r.pulses" :key="c.node + c.id" class="cursor-pointer text-xs"
                          :class="isOpen(c) ? 'bg-primary-50 dark:bg-primary-950/40' : 'bg-gray-50 dark:bg-gray-800/40 hover:bg-gray-100 dark:hover:bg-gray-800'"
                          @click="showCandidate(c)">
                          <td class="pl-8 pr-2 py-1 whitespace-nowrap">{{ bandName(c.node) }}</td>
                          <td class="px-2 py-1 text-right tabular-nums">{{ c.dm.toFixed(1) }}</td>
                          <td class="px-2 py-1" />
                          <td class="px-2 py-1" />
                          <td class="px-2 py-1 text-right tabular-nums">{{ c.snr.toFixed(1) }}</td>
                          <td class="px-2 py-1 font-mono whitespace-nowrap">{{ tz.dateTime(c.t_inf * 1000) }}</td>
                        </tr>
                      </template>
                    </template>
                    <tr v-if="!shownPulsarRows.length"><td colspan="6" class="px-2 py-3 text-center text-gray-500">
                      {{ pulsarRows.length ? 'No pulses from any pulsar in this period.' : 'No monitor answered with its pulsars.' }}</td></tr>
                  </tbody>
                </table>
              </div>
            </template>
          </UTabs>
        </UCard>
      </div>

      <!-- right: the spectrogram of what is selected, kept in view -->
      <div ref="viewer" class="min-w-0 p-px xl:sticky xl:top-0 xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto">
        <UCard :ui="{ body: { padding: 'p-2 sm:p-3' }, header: { padding: 'px-3 py-2 sm:px-4' } }">
          <template #header>
            <div class="flex flex-wrap items-center gap-3">
              <span class="font-medium">{{ openCand ? viewerTitle : 'Spectrogram' }}</span>
              <span v-if="openCand" class="text-sm text-gray-500 dark:text-gray-400">{{ bandName(openCand.node) }}</span>
              <span v-else-if="selNode" class="text-sm text-gray-500 dark:text-gray-400">{{ bandName(selNode.node) }}</span>
              <div class="flex-1" />
              <template v-if="ra != null && dec != null">
                <UButtonGroup size="xs" orientation="horizontal">
                  <UButton v-for="m in viewModes" :key="m.value" :label="m.label"
                    :color="viewMode == m.value ? 'primary' : 'gray'" :variant="viewMode == m.value ? 'solid' : 'outline'"
                    @click="setView(m.value)" />
                </UButtonGroup>
                <USelect v-if="viewMode == 'avg'" v-model="specHours" size="xs"
                  :options="[{ label: 'last 30 min', value: 0.5 }, { label: 'last 1 h', value: 1 }, { label: 'last 2 h', value: 2 }, { label: 'last 6 h', value: 6 }]" />
              </template>
            </div>
          </template>
          <SpectrogramSkymonCandidate v-if="openCand" :node="openCand.node" :id="openCand.id" />
          <SpectrogramSkymonSpectrogram v-else-if="node && ra != null && dec != null" :node="node" :ra="ra" :dec="dec"
            :hpix="pickedHpix" :dt-image="selNode?.band?.dt" :t-inf="mark?.tInf" :dm="mark?.dm" />
          <p v-else class="text-center text-gray-500 dark:text-gray-400 py-16">Select a pixel, a candidate or a pulse.</p>
        </UCard>
      </div>
    </div>
  </UDashboardPanelContent>
</template>
