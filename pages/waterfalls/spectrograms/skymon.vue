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
const showUnconfirmable = ref(false)
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
function bandText(name: string, b: BandState) {
  const v = b.candidate?.snr ?? b.followup?.snr
  const f = b.candidate?.fluence_jy_ms ?? b.followup?.fluence_jy_ms
  return `${name} ${bandLabel[b.state ?? ''] ?? b.state ?? ''}${v != null ? ' ' + v.toFixed(1) : ''}` +
    (f != null ? `, ${fluenceText(f)}` : '')
}
function solarText(r: Solar) {
  const t = (iso?: string | null) => iso ? tz.dateTime(Date.parse(iso)) : ''
  const kind = r.type == 'XRA' ? `X-ray flare${r.cls ? ' ' + r.cls : ''}` : `radio burst${r.cls ? ' type ' + r.cls : ''}`
  return `${kind}, ${t(r.begin)}${r.end ? ' to ' + t(r.end) : ''}`
}
function fluenceText(f: number) {
  return f >= 1000 ? `${(f / 1000).toFixed(1)} Jy s` : `${f.toPrecision(3)} Jy ms`
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
const raInput = ref(ra.value != null ? ra.value.toFixed(3) : '')
const decInput = ref(dec.value != null ? dec.value.toFixed(3) : '')
const mark = ref<{ tInf: number, dm: number } | null>(null)
// a candidate whose kept data are shown instead of the live pixel
const openCand = ref<{ node: string, id: string } | null>(typeof route.query.cand == 'string' && route.query.cand.includes(':')
  ? { node: route.query.cand.split(':')[0], id: route.query.cand.split(':').slice(1).join(':') } : null)
const skyMap = ref<{ centreOn: (ra: number, dec: number) => void } | null>(null)
const positionError = computed(() => {
  if (raInput.value === '' && decInput.value === '') return ''
  const r = Number(raInput.value), d = Number(decInput.value)
  if (!(r >= 0 && r < 360)) return 'Right ascension is in degrees, from 0 up to 360.'
  if (!(d >= -90 && d <= 90)) return 'Declination is in degrees, from −90 to 90.'
  return ''
})
function setPosition(r: number, d: number, hpix: number | null = null) {
  ra.value = r
  dec.value = d
  pickedHpix.value = hpix
  raInput.value = r.toFixed(3)
  decInput.value = d.toFixed(3)
}
function showPosition() {
  if (positionError.value || raInput.value === '' || decInput.value === '') return
  setPosition(Number(raInput.value), Number(decInput.value))
  mark.value = null
  openCand.value = null
  skyMap.value?.centreOn(ra.value!, dec.value!)
}
function onPick(p: { hpix: number, nside: number, ra: number, dec: number }) {
  setPosition(p.ra, p.dec, p.hpix)
  mark.value = null
  openCand.value = null
}
function selectNode(n: string) {
  if (n == node.value) return
  node.value = n
  pickedHpix.value = null  // the pixel of this position on the new monitor's grid
}
function showCandidate(c: Cand) {
  if (c.node) selectNode(c.node)
  setPosition(c.ra, c.dec)
  mark.value = { tInf: c.t_inf, dm: c.dm }
  openCand.value = c.node && c.id ? { node: c.node, id: c.id } : null
  skyMap.value?.centreOn(c.ra, c.dec)
}
watch([node, ra, dec, sinceH, showInjections, openCand], () => {
  const q: Record<string, string> = {}
  if (node.value) q.node = node.value
  if (openCand.value) q.cand = `${openCand.value.node}:${openCand.value.id}`
  if (ra.value != null && dec.value != null) { q.ra = ra.value.toFixed(4); q.dec = dec.value.toFixed(4) }
  if (sinceH.value != 24) q.since_h = String(sinceH.value)
  if (showInjections.value) q.inj = '1'
  router.replace({ query: q })
})
// candidates of the shown monitor, marked on its sky
const markers = computed(() => cands.value
  .filter(c => c.node == node.value && (c.cls == 'candidate' || (showInjections.value && c.cls == 'injection')))
  .map(c => ({ ra: c.ra, dec: c.dec, color: c.cls == 'injection' ? '#38bdf8' : '#f59e0b', title: `S/N ${c.snr.toFixed(1)}, DM ${c.dm.toFixed(1)}` })))
const candCount = (n: Node) => n.candidates ? n.candidates.stored - n.candidates.rfi - n.candidates.injection : null
const dmReach = (n: Node) => n.tiers?.length ? Math.round(n.tiers[n.tiers.length - 1].dm_max) : null
watch(sinceH, () => { loadCands(); loadEvents() })

const pct = (x?: number | null) => x == null ? '' : `${Math.round(100 * x)}%`
const fmt = (x?: number | null, d = 1) => x == null ? '' : x.toFixed(d)
const clsLabel: Record<string, string> = { candidate: 'Candidate', injection: 'Test injection', rfi: 'RFI', known: 'Known source' }
const clsColor: Record<string, string> = { candidate: 'amber', injection: 'sky', rfi: 'gray', known: 'violet' }
const knownLabel: Record<string, string> = { solar: 'Sun', jovian: 'Jupiter', bright_source: '', pulsar: 'pulsar' }
function clsText(c: Cand) {
  if (c.cls == 'known' && c.known_source?.kind == 'pulsar') {
    const ks = c.known_source
    return ks.giant_pulse ? 'giant pulse' : 'single pulse'  // after the pulsar's name (SkymonPulsarName)
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
    const known = await $fetch<Cand[]>(rtConfig.public.fastapiBase + '/skymon/candidates', { query: { since_h: sinceH.value, cls: 'known', limit: 5000 } })
    pulses.value = known.filter(c => c.known_source?.kind == 'pulsar')
  } catch { pulses.value = [] }
  finally { pulsesPending.value = false }
}
const pulsarRows = computed(() => pulsars.value.map(p => {
  const mine = pulses.value.filter(c => c.known_source?.name == p.name)
  const brightest = mine.reduce<Cand | null>((a, c) => !a || c.snr > a.snr ? c : a, null)
  const last = mine.reduce<Cand | null>((a, c) => !a || c.t_inf > a.t_inf ? c : a, null)
  return { p, n: mine.length, brightest, last }
}).sort((a, b) => b.n - a.n || Number(!!b.p.giant_pulses) - Number(!!a.p.giant_pulses) || a.p.name.localeCompare(b.p.name)))
const mapPulsars = computed(() => pulsars.value.map(p => ({ ra: p.ra_deg, dec: p.dec_deg, label: pulsarLabel(p.name), icon: hasIcon(p.name) })))
watch(sinceH, loadPulsars)

// refreshed every minute while the page is open (in the browser only)
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  tz.restore()
  try { canReview.value = !!hanko?.session.isValid() } catch { canReview.value = false }
  loadNodes()
  loadCands()
  loadEvents()
  loadPulsars()
  timer = setInterval(() => { loadNodes(); loadCands(); loadEvents(); loadPulsars() }, 60000)
})
onBeforeUnmount(() => clearInterval(timer))

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
    <template #right><TimeZoneToggle /></template>
  </PageToolbar>
  <UDashboardPanelContent class="space-y-4">
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <UCard :ui="{ body: { padding: 'p-2 sm:p-3' } }">
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-medium">Sky</span>
            <span v-if="selNode" class="text-sm text-gray-500 dark:text-gray-400">
              seen by {{ selNode.node }}<template v-if="selNode.band"> at {{ selNode.band.f_lo.toFixed(2) }}–{{ selNode.band.f_hi.toFixed(2) }} MHz</template>, last 5 min
            </span>
          </div>
        </template>
        <SpectrogramSkymonSkyMap ref="skyMap" :node="node" :waiting="!nodesLoaded" :selected="selectedHpix" :markers="markers" :pulsars="mapPulsars"
          @select="onPick" @nside="n => mapNside = n" />
      </UCard>

      <UCard :ui="{ body: { padding: 'p-2 sm:p-3' } }">
        <template #header>
          <div class="flex items-center gap-2">
            <span class="font-medium">Monitors</span>
            <span class="text-sm text-gray-500 dark:text-gray-400">one per imaging band; select one to show its sky</span>
            <div class="flex-1" />
            <UButton size="xs" variant="ghost" icon="i-heroicons-arrow-path" :loading="nodesPending" @click="loadNodes" />
          </div>
        </template>
        <SpectrogramSkymonLoading v-if="!nodesLoaded" :messages="[
          'Asking the six monitors for their state',
          'Collecting bands, tracked pixels and candidates',
          'Waiting for the slower monitors to answer']" />
        <div v-else class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead class="text-left text-gray-500 dark:text-gray-400">
              <tr>
                <th class="px-2 py-1">Node</th><th class="px-2 py-1">State</th><th class="px-2 py-1">Band (MHz)</th>
                <th class="px-2 py-1 text-right">Tracked pixels</th><th class="px-2 py-1 text-right">DM reach (pc cm⁻³)</th>
                <th class="px-2 py-1 text-right">Candidates</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="n in nodes" :key="n.node" class="border-t border-gray-200 dark:border-gray-800 cursor-pointer"
                :class="n.node == node ? 'bg-primary-50 dark:bg-primary-950/40' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'"
                @click="selectNode(n.node)">
                <td class="px-2 py-1 font-mono">{{ n.node }}</td>
                <td class="px-2 py-1">
                  <UBadge :color="!n.up ? 'red' : n.conditions?.latest?.disturbed ? 'orange' : 'green'" variant="subtle" size="xs"
                    :label="!n.up ? 'Not answering' : n.conditions?.latest?.disturbed ? 'Disturbed' : 'Running'" />
                </td>
                <td class="px-2 py-1 tabular-nums">{{ n.band ? `${n.band.f_lo.toFixed(2)}–${n.band.f_hi.toFixed(2)}` : '' }}</td>
                <td class="px-2 py-1 text-right tabular-nums">{{ n.tracked ?? '' }}</td>
                <td class="px-2 py-1 text-right tabular-nums">{{ dmReach(n) ?? '' }}</td>
                <td class="px-2 py-1 text-right tabular-nums">{{ candCount(n) ?? '' }}</td>
              </tr>
              <tr v-if="!nodes.length && !nodesPending"><td colspan="6" class="px-2 py-3 text-center text-gray-500">No monitor answered.</td></tr>
            </tbody>
          </table>
        </div>
        <div v-if="selNode?.up" class="mt-3 border-t border-gray-200 dark:border-gray-800 pt-3">
          <div class="text-sm font-medium mb-2">{{ selNode.node }}</div>
          <dl class="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 text-sm">
            <div><dt class="text-gray-500 dark:text-gray-400">Channels</dt><dd class="tabular-nums">{{ selNode.band?.nchan ?? '' }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">Image time (ms)</dt><dd class="tabular-nums">{{ selNode.band ? (selNode.band.dt * 1000).toFixed(1) : '' }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">HEALPix nside</dt><dd class="tabular-nums">{{ selNode.nside ?? '' }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">Beam (°)</dt><dd class="tabular-nums">{{ fmt(selNode.beam_deg) }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">Threshold (S/N)</dt><dd class="tabular-nums">{{ fmt(selNode.threshold) }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">Compute load</dt><dd class="tabular-nums">{{ pct(selNode.cpu_fraction) }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">Lag (s)</dt><dd class="tabular-nums">{{ fmt(selNode.lag_s) }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">Images missing</dt><dd class="tabular-nums">{{ selNode.images ? pct((selNode.missing_images ?? 0) / (selNode.images + (selNode.missing_images ?? 0))) : '' }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">Channels flagged</dt>
              <dd class="tabular-nums" :title="selNode.rfi_flagging?.masked_mhz?.length ? `Masked at ${selNode.rfi_flagging.masked_mhz.map(f => f.toFixed(3)).join(', ')} MHz` : undefined">
                {{ pct(selNode.rfi_flagging?.flagged_fraction_last_minute) }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">RFI candidates</dt><dd class="tabular-nums">{{ selNode.candidates?.rfi ?? '' }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">Test injections found</dt>
              <dd class="tabular-nums">{{ selNode.injections?.injected ? `${selNode.injections.recovered} of ${selNode.injections.recovered + selNode.injections.missed}` : '' }}</dd></div>
            <div><dt class="text-gray-500 dark:text-gray-400">Last image ({{ tz.zoneName() }})</dt>
              <dd class="tabular-nums">{{ selNode.last_image_unix ? tz.clock(selNode.last_image_unix * 1000) : '' }}</dd></div>
          </dl>
          <p v-if="selNode.conditions?.latest?.disturbed" class="mt-2 text-xs text-orange-600 dark:text-orange-400">
            Disturbed<template v-if="selNode.conditions.latest.reasons?.length"> by {{ selNode.conditions.latest.reasons.map(r => reasonLabel[r] ?? r).join(', ') }}</template><template v-if="selNode.conditions.summary?.disturbed_since"> since {{ tz.dateTime(selNode.conditions.summary.disturbed_since * 1000) }}</template>.
          </p>
        </div>
        <p v-else-if="selNode" class="mt-3 text-sm text-gray-500 dark:text-gray-400">The monitor on {{ selNode.node }} is not answering.</p>
      </UCard>
    </div>

    <UCard :ui="{ body: { padding: 'p-2 sm:p-3' } }">
      <template #header>
        <div class="flex flex-wrap items-center gap-3">
          <span class="font-medium">{{ openCand ? 'Candidate' : 'Spectrogram' }}</span>
          <span v-if="openCand" class="text-sm text-gray-500 dark:text-gray-400">{{ openCand.node }}, {{ openCand.id }}</span>
          <span v-else-if="selNode" class="text-sm text-gray-500 dark:text-gray-400">{{ selNode.node }}, live pixel</span>
          <div class="flex-1" />
          <UInput v-model="raInput" placeholder="RA (°)" size="xs" class="w-28" @keyup.enter="showPosition" />
          <UInput v-model="decInput" placeholder="Dec (°)" size="xs" class="w-28" @keyup.enter="showPosition" />
          <UButton size="xs" variant="outline" label="Display" :disabled="!!positionError || raInput === '' || decInput === ''" @click="showPosition" />
          <span v-if="positionError" class="text-xs text-red-500">{{ positionError }}</span>
        </div>
      </template>
      <SpectrogramSkymonCandidate v-if="openCand" :node="openCand.node" :id="openCand.id"
        @live="openCand = null; mark = null" />
      <SpectrogramSkymonSpectrogram v-else-if="node && ra != null && dec != null" :node="node" :ra="ra" :dec="dec"
        :hpix="pickedHpix" :dt-image="selNode?.band?.dt" :t-inf="mark?.tInf" :dm="mark?.dm" />
      <p v-else class="text-center text-gray-500 dark:text-gray-400 py-6">
        Click a pixel on the sky, enter a position, or open the spectrogram of a candidate.
      </p>
    </UCard>

    <UCard :ui="{ body: { padding: 'p-2 sm:p-3' } }">
      <template #header>
        <div class="flex flex-wrap items-center gap-3">
          <span class="font-medium">Pulsars</span>
          <span class="text-sm text-gray-500 dark:text-gray-400">
            single pulses found at the position and DM of a known pulsar, in the last {{ sinceOptions.find(o => o.value == sinceH)?.label ?? `${sinceH} hours` }}
          </span>
        </div>
      </template>
      <SpectrogramSkymonLoading v-if="pulsesPending" compact :messages="['Asking the monitors for their pulsars', 'Collecting the single pulses of each']" />
      <div v-else class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="text-left text-gray-500 dark:text-gray-400">
            <tr>
              <th class="px-2 py-1">Pulsar</th><th class="px-2 py-1 text-right">DM (pc cm⁻³)</th><th class="px-2 py-1 text-right">Period (s)</th>
              <th class="px-2 py-1 text-right">Pulses</th><th class="px-2 py-1 text-right">Brightest S/N</th>
              <th class="px-2 py-1">Last pulse ({{ tz.zoneName() }})</th><th class="px-2 py-1" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in pulsarRows" :key="r.p.name" class="border-t border-gray-200 dark:border-gray-800">
              <td class="px-2 py-1">
                <SpectrogramSkymonPulsarName :name="r.p.name" :alias="r.p.alias" :size="26" />
                <span v-if="r.p.giant_pulses" class="ml-2 text-xs text-gray-500 dark:text-gray-400">giant pulses</span>
              </td>
              <td class="px-2 py-1 text-right tabular-nums">{{ r.p.dm.toFixed(2) }}</td>
              <td class="px-2 py-1 text-right tabular-nums">{{ r.p.period_s != null ? r.p.period_s.toFixed(4) : '' }}</td>
              <td class="px-2 py-1 text-right tabular-nums">{{ r.n || '' }}</td>
              <td class="px-2 py-1 text-right tabular-nums">{{ r.brightest ? r.brightest.snr.toFixed(1) : '' }}</td>
              <td class="px-2 py-1 font-mono">{{ r.last ? tz.dateTime(r.last.t_inf * 1000) : '' }}</td>
              <td class="px-2 py-1"><UButton v-if="r.brightest" size="2xs" variant="outline" label="Brightest pulse" @click="showCandidate(r.brightest)" /></td>
            </tr>
            <tr v-if="!pulsarRows.length"><td colspan="7" class="px-2 py-3 text-center text-gray-500">No monitor answered with its pulsars.</td></tr>
          </tbody>
        </table>
      </div>
    </UCard>

    <UCard :ui="{ body: { padding: 'p-2 sm:p-3' } }">
      <template #header>
        <div class="flex flex-wrap items-center gap-3">
          <span class="font-medium">Events across bands</span>
          <span class="text-sm text-gray-500 dark:text-gray-400">each candidate checked in every band that could see it</span>
          <UCheckbox v-model="showInjEvents" label="Test injections" />
          <UCheckbox v-model="showUnconfirmable" label="Not checkable" />
          <UCheckbox v-model="showReviewed" label="Already reviewed" />
          <UCheckbox v-model="showTerrestrial" label="Terrestrial" />
          <div class="flex-1" />
          <UBadge v-if="combinerUp === false" color="red" variant="subtle" size="xs" label="Combiner not answering" />
          <UButton size="xs" variant="ghost" icon="i-heroicons-arrow-path" :loading="eventsPending" @click="loadEvents" />
        </div>
      </template>
      <div class="overflow-x-auto max-h-96">
        <table class="min-w-full text-sm">
          <thead class="text-left text-gray-500 dark:text-gray-400 sticky top-0 bg-white dark:bg-gray-900">
            <tr>
              <th class="px-2 py-1">Arrival at infinite frequency ({{ tz.zoneName() }})</th><th class="px-2 py-1">Result</th>
              <th class="px-2 py-1 text-right">DM (pc cm⁻³)</th><th class="px-2 py-1 text-right">Combined S/N</th>
              <th class="px-2 py-1 text-right">RA (°)</th><th class="px-2 py-1 text-right">Dec (°)</th>
              <th class="px-2 py-1">Bands</th><th class="px-2 py-1" />
            </tr>
          </thead>
          <tbody>
            <template v-for="e in shownEvents" :key="e.id">
              <tr class="border-t border-gray-200 dark:border-gray-800 cursor-pointer" @click="expanded = expanded == e.id ? null : e.id">
                <td class="px-2 py-1 font-mono">{{ tz.dateTime(e.t_inf * 1000) }}</td>
                <td class="px-2 py-1">
                  <UBadge :color="evColor[e.status]" variant="subtle" size="xs" :label="evLabel[e.status] ?? e.status" />
                  <UBadge v-if="e.kind == 'injection'" color="sky" variant="outline" size="xs" label="Test injection" class="ml-1" />
                  <UBadge v-if="reviewLabel[e.review ?? '']" :color="e.review == 'pending' ? 'orange' : 'gray'" variant="outline" size="xs"
                    :label="reviewLabel[e.review ?? '']" class="ml-1" />
                  <UBadge v-if="e.disturbed" color="orange" variant="outline" size="xs" label="Band disturbed" class="ml-1" />
                  <UBadge v-if="e.other_dm?.length" color="violet" variant="outline" size="xs" label="Other DMs here" class="ml-1" />
                </td>
                <td class="px-2 py-1 text-right">{{ e.dm != null ? `${e.dm.toFixed(1)} ± ${(e.dm_err ?? 0).toFixed(1)}` : '' }}</td>
                <td class="px-2 py-1 text-right">{{ e.combined_snr != null ? e.combined_snr.toFixed(1) : '' }}</td>
                <td class="px-2 py-1 text-right">{{ fmt(e.ra, 2) }}</td>
                <td class="px-2 py-1 text-right">{{ fmt(e.dec, 2) }}</td>
                <td class="px-2 py-1">{{ e.kind == 'terrestrial' ? `${e.candidates?.length ?? 0} candidates` : e.seen?.length ? `seen in ${e.seen.length} of ${e.could_see?.length ?? 0}` : '' }}</td>
                <td class="px-2 py-1"><UButton v-if="e.ra != null" size="2xs" variant="outline" label="Spectrogram" @click.stop="showEvent(e)" /></td>
              </tr>
              <tr v-if="expanded == e.id" class="bg-gray-50 dark:bg-gray-800/50">
                <td colspan="8" class="px-4 py-2 space-y-2">
                  <div class="flex flex-wrap gap-2">
                    <UBadge v-for="(b, name) in e.bands" :key="name" size="xs" variant="soft"
                      :color="b.state == 'detected' || (b.state == 'followup' && (b.followup?.snr ?? 0) >= 6) ? 'green' : b.state == 'watching' ? 'sky' : 'gray'"
                      :label="bandText(String(name), b) + (b.state == 'detected' || b.data_id ? ', data kept' : '')" />
                  </div>
                  <p v-if="e.spectrum?.consistent_with?.length" class="text-xs text-gray-600 dark:text-gray-300">
                    The S/N measured in the bands is consistent with {{ e.spectrum.consistent_with.join(', or with ') }}.
                  </p>
                  <p v-if="e.kind == 'terrestrial'" class="text-xs text-gray-600 dark:text-gray-300">
                    {{ e.reason }}<template v-if="e.candidates?.length">. Candidates
                      {{ e.candidates.map(c => `${c.node} S/N ${c.snr.toFixed(1)} at DM ${c.dm.toFixed(1)}`).join(', ') }}.</template>
                  </p>
                  <p v-if="e.other_dm?.length" class="text-xs text-gray-600 dark:text-gray-300">
                    Also found at this position during the sweep, at other DMs, with data kept
                    {{ e.other_dm.map(o => `${o.node} S/N ${o.snr.toFixed(1)} at DM ${o.dm.toFixed(1)}`).join(', ') }}.
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
                      <UInput v-model="reviewNote" size="xs" placeholder="Note (optional)" class="w-72" @click.stop />
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
            <tr v-if="!shownEvents.length && eventsPending"><td colspan="8">
              <SpectrogramSkymonLoading compact :messages="['Asking the combiner for the events', 'Collecting the bands of each event']" /></td></tr>
            <tr v-if="!shownEvents.length && !eventsPending"><td colspan="8" class="px-2 py-3 text-center text-gray-500">No events in this period.</td></tr>
          </tbody>
        </table>
      </div>
    </UCard>

    <UCard :ui="{ body: { padding: 'p-2 sm:p-3' } }">
      <template #header>
        <div class="flex flex-wrap items-center gap-3">
          <span class="font-medium">Candidates</span>
          <USelect v-model="sinceH" :options="sinceOptions" size="xs" />
          <UCheckbox v-model="showInjections" label="Test injections" />
          <UCheckbox v-model="showRfi" label="RFI" />
          <UCheckbox v-model="showKnown" label="Known sources" />
          <div class="flex-1" />
          <UButton size="xs" variant="ghost" icon="i-heroicons-arrow-path" :loading="candsPending" @click="loadCands" />
        </div>
      </template>
      <div class="overflow-x-auto max-h-96">
        <table class="min-w-full text-sm">
          <thead class="text-left text-gray-500 dark:text-gray-400 sticky top-0 bg-white dark:bg-gray-900">
            <tr>
              <th class="px-2 py-1">Arrival at infinite frequency ({{ tz.zoneName() }})</th><th class="px-2 py-1">Band</th>
              <th class="px-2 py-1 text-right">S/N</th><th class="px-2 py-1 text-right">DM (pc cm⁻³)</th>
              <th class="px-2 py-1 text-right">Width (s)</th><th class="px-2 py-1 text-right">Fluence</th>
              <th class="px-2 py-1 text-right">RA (°)</th>
              <th class="px-2 py-1 text-right">Dec (°)</th><th class="px-2 py-1 text-right">Elevation (°)</th>
              <th class="px-2 py-1">Class</th><th class="px-2 py-1" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in shownCands" :key="c.node + c.id" class="border-t border-gray-200 dark:border-gray-800">
              <td class="px-2 py-1 font-mono">{{ tz.dateTime(c.t_inf * 1000) }}</td>
              <td class="px-2 py-1">{{ c.node }}, {{ ((c.f_lo_mhz + c.f_hi_mhz) / 2).toFixed(1) }} MHz</td>
              <td class="px-2 py-1 text-right">{{ c.snr.toFixed(1) }}</td>
              <td class="px-2 py-1 text-right">{{ c.dm.toFixed(1) }}</td>
              <td class="px-2 py-1 text-right">{{ c.width_s.toFixed(2) }}</td>
              <td class="px-2 py-1 text-right" :title="c.flux?.fluence_err_jy_ms != null ? `Uncertainty from the S/N ${fluenceText(c.flux.fluence_err_jy_ms)}` : undefined">
                {{ c.flux ? fluenceText(c.flux.fluence_jy_ms) : '' }}
              </td>
              <td class="px-2 py-1 text-right">{{ c.ra.toFixed(2) }}</td>
              <td class="px-2 py-1 text-right">{{ c.dec.toFixed(2) }}</td>
              <td class="px-2 py-1 text-right">{{ c.el.toFixed(0) }}</td>
              <td class="px-2 py-1">
                <UBadge :color="clsColor[c.cls]" variant="subtle" size="xs" :label="clsLabel[c.cls] ?? c.cls" />
                <SpectrogramSkymonPulsarName v-if="c.cls == 'known' && c.known_source?.kind == 'pulsar'" class="ml-1 text-xs"
                  :name="c.known_source.name" :alias="c.known_source.alias" :size="18" />
                <span v-if="clsText(c)" class="ml-1 text-xs text-gray-500 dark:text-gray-400">{{ clsText(c) }}</span>
              </td>
              <td class="px-2 py-1"><UButton size="2xs" variant="outline" label="Spectrogram" @click="showCandidate(c)" /></td>
            </tr>
            <tr v-if="!shownCands.length && candsPending"><td colspan="11">
              <SpectrogramSkymonLoading compact :messages="['Asking every monitor for its candidates', 'Merging the candidates of all bands']" /></td></tr>
            <tr v-if="!shownCands.length && !candsPending"><td colspan="11" class="px-2 py-3 text-center text-gray-500">No candidates in this period.</td></tr>
          </tbody>
        </table>
      </div>
    </UCard>

  </UDashboardPanelContent>
</template>
