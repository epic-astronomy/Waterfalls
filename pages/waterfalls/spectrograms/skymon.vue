<script setup lang="ts">
// All-sky monitor: every imaging worker searches its own band of the whole
// visible sky for dispersed bursts. This page shows the state of each
// monitor, the candidates they found, and the spectrogram of any position.
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
  injections?: { injected: number, recovered: number, missed: number, active: number },
  tiers?: { dm_max: number }[]
}
interface Cand {
  id: string, node: string, cls: string, snr: number, dm: number, width_s: number, t_inf: number,
  utc_inf: string, ra: number, dec: number, el: number, tier: number, n_pix: number,
  f_lo_mhz: number, f_hi_mhz: number, injection_id?: string | null
}

const nodes = ref<Node[]>([])
const nodesPending = ref(false)
async function loadNodes() {
  nodesPending.value = true
  try { nodes.value = await $fetch<Node[]>(rtConfig.public.fastapiBase + '/skymon/nodes') }
  catch { nodes.value = [] }
  finally { nodesPending.value = false }
}

// events of the combiner: candidates checked in every band that could see them
interface BandState {
  state?: string, f_lo?: number, f_hi?: number, el_at_arrival?: number, predicted_t_bottom?: number,
  reason?: string, candidate?: { snr: number, dm: number }, followup?: { snr: number, dm: number }
}
interface Ev {
  id: string, kind: string, status: string, ra: number, dec: number, dm: number, dm_err: number,
  t_inf: number, combined_snr: number | null, best_snr?: number | null, seen?: string[], could_see?: string[],
  bands: Record<string, BandState & { data_id?: string }>,
  spectrum?: { plausible: boolean | null, consistent_with?: string[] },
  review?: string, reviews?: { verdict: string, by: string, note: string, at: number }[]
}
const events = ref<Ev[]>([])
const combinerUp = ref<boolean | null>(null)
const eventsPending = ref(false)
const showInjEvents = ref(false)
const showUnconfirmable = ref(false)
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
  (showReviewed.value || e.review == 'pending')))
const evLabel: Record<string, string> = {
  pending: 'Pending', confirmed: 'Confirmed', band_limited: 'One band, plausible spectrum',
  implausible: 'One band, implausible spectrum', unconfirmable: 'Not checkable', single_band: 'One band'
}
const evColor: Record<string, string> = {
  pending: 'sky', confirmed: 'green', band_limited: 'amber', implausible: 'gray', unconfirmable: 'gray', single_band: 'amber'
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
  return `${name} ${bandLabel[b.state ?? ''] ?? b.state ?? ''}${v != null ? ' ' + v.toFixed(1) : ''}`
}
function showEvent(e: Ev) {
  showCandidate({ ra: e.ra, dec: e.dec, t_inf: e.t_inf, dm: e.dm } as Cand)
}
const expanded = ref<string | null>(null)

const sinceH = ref(Number(route.query.since_h) || 24)
const showInjections = ref(route.query.inj == '1')
const showRfi = ref(false)
const cands = ref<Cand[]>([])
const candsPending = ref(false)
async function loadCands() {
  candsPending.value = true
  try { cands.value = await $fetch<Cand[]>(rtConfig.public.fastapiBase + '/skymon/candidates', { query: { since_h: sinceH.value } }) }
  catch { cands.value = [] }
  finally { candsPending.value = false }
}
const shownCands = computed(() => cands.value.filter(c =>
  (c.cls == 'candidate') || (showInjections.value && c.cls == 'injection') || (showRfi.value && c.cls == 'rfi')))

const sinceOptions = [{ label: '6 hours', value: 6 }, { label: '24 hours', value: 24 }, { label: '3 days', value: 72 }, { label: '7 days', value: 168 }]

// spectrogram of a position, from the address so it can be shared
const ra = ref(route.query.ra != null ? Number(route.query.ra) : null as number | null)
const dec = ref(route.query.dec != null ? Number(route.query.dec) : null as number | null)
const hours = ref(Number(route.query.hours) || 2)
const raInput = ref(ra.value != null ? String(ra.value) : '')
const decInput = ref(dec.value != null ? String(dec.value) : '')
const mark = ref<{ tInf: number, dm: number } | null>(null)
const positionError = computed(() => {
  if (raInput.value === '' && decInput.value === '') return ''
  const r = Number(raInput.value), d = Number(decInput.value)
  if (!(r >= 0 && r < 360)) return 'Right ascension is in degrees, from 0 up to 360.'
  if (!(d >= -90 && d <= 90)) return 'Declination is in degrees, from −90 to 90.'
  return ''
})
function showPosition() {
  if (positionError.value || raInput.value === '' || decInput.value === '') return
  ra.value = Number(raInput.value)
  dec.value = Number(decInput.value)
  mark.value = null
}
function showCandidate(c: Cand) {
  raInput.value = c.ra.toFixed(3)
  decInput.value = c.dec.toFixed(3)
  ra.value = c.ra
  dec.value = c.dec
  mark.value = { tInf: c.t_inf, dm: c.dm }
  const age_h = (Date.now() / 1000 - c.t_inf) / 3600
  hours.value = Math.min(6, Math.max(1, Math.ceil(age_h + 0.5)))
}
watch([ra, dec, hours, sinceH, showInjections], () => {
  const q: Record<string, string> = {}
  if (ra.value != null && dec.value != null) { q.ra = String(ra.value); q.dec = String(dec.value); q.hours = String(hours.value) }
  if (sinceH.value != 24) q.since_h = String(sinceH.value)
  if (showInjections.value) q.inj = '1'
  router.replace({ query: q })
})
watch(sinceH, () => { loadCands(); loadEvents() })

const pct = (x?: number | null) => x == null ? '' : `${Math.round(100 * x)}%`
const fmt = (x?: number | null, d = 1) => x == null ? '' : x.toFixed(d)
const clsLabel: Record<string, string> = { candidate: 'Candidate', injection: 'Test injection', rfi: 'RFI' }
const clsColor: Record<string, string> = { candidate: 'amber', injection: 'sky', rfi: 'gray' }

// refreshed every minute while the page is open (in the browser only)
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  tz.restore()
  try { canReview.value = !!hanko?.session.isValid() } catch { canReview.value = false }
  loadNodes()
  loadCands()
  loadEvents()
  timer = setInterval(() => { loadNodes(); loadCands(); loadEvents() }, 60000)
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
    <UCard :ui="{ body: { padding: 'p-2 sm:p-3' } }">
      <template #header>
        <div class="flex items-center gap-2">
          <span class="font-medium">Monitors</span>
          <span class="text-sm text-gray-500 dark:text-gray-400">one per imaging band, each independent of the others</span>
          <div class="flex-1" />
          <UButton size="xs" variant="ghost" icon="i-heroicons-arrow-path" :loading="nodesPending" @click="loadNodes" />
        </div>
      </template>
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="text-left text-gray-500 dark:text-gray-400">
            <tr>
              <th class="px-2 py-1">Node</th><th class="px-2 py-1">State</th><th class="px-2 py-1">Band (MHz)</th>
              <th class="px-2 py-1 text-right">Tracked pixels</th><th class="px-2 py-1 text-right">Beam (°)</th>
              <th class="px-2 py-1 text-right">DM reach</th><th class="px-2 py-1 text-right">Compute load</th>
              <th class="px-2 py-1 text-right">Lag (s)</th><th class="px-2 py-1 text-right">Candidates</th>
              <th class="px-2 py-1 text-right">Test injections found</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="n in nodes" :key="n.node" class="border-t border-gray-200 dark:border-gray-800">
              <td class="px-2 py-1 font-mono">{{ n.node }}</td>
              <td class="px-2 py-1">
                <UBadge :color="n.up ? 'green' : 'red'" variant="subtle" size="xs" :label="n.up ? 'Running' : 'Not answering'" />
              </td>
              <td class="px-2 py-1">{{ n.band ? `${n.band.f_lo.toFixed(2)}–${n.band.f_hi.toFixed(2)}` : '' }}</td>
              <td class="px-2 py-1 text-right">{{ n.tracked ?? '' }}</td>
              <td class="px-2 py-1 text-right">{{ fmt(n.beam_deg) }}</td>
              <td class="px-2 py-1 text-right">{{ n.tiers?.length ? Math.round(n.tiers[n.tiers.length - 1].dm_max) : '' }}</td>
              <td class="px-2 py-1 text-right">{{ pct(n.cpu_fraction) }}</td>
              <td class="px-2 py-1 text-right">{{ fmt(n.lag_s) }}</td>
              <td class="px-2 py-1 text-right">{{ n.candidates ? n.candidates.stored - n.candidates.rfi - n.candidates.injection : '' }}</td>
              <td class="px-2 py-1 text-right">{{ n.injections?.injected ? `${n.injections.recovered} of ${n.injections.recovered + n.injections.missed}` : '' }}</td>
            </tr>
            <tr v-if="!nodes.length && !nodesPending"><td colspan="10" class="px-2 py-3 text-center text-gray-500">No monitor answered.</td></tr>
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
                </td>
                <td class="px-2 py-1 text-right">{{ e.dm.toFixed(1) }} ± {{ e.dm_err.toFixed(1) }}</td>
                <td class="px-2 py-1 text-right">{{ e.combined_snr != null ? e.combined_snr.toFixed(1) : '' }}</td>
                <td class="px-2 py-1 text-right">{{ e.ra.toFixed(2) }}</td>
                <td class="px-2 py-1 text-right">{{ e.dec.toFixed(2) }}</td>
                <td class="px-2 py-1">{{ e.seen?.length ? `seen in ${e.seen.length} of ${e.could_see?.length ?? 0}` : '' }}</td>
                <td class="px-2 py-1"><UButton size="2xs" variant="outline" label="Spectrogram" @click.stop="showEvent(e)" /></td>
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
              <th class="px-2 py-1 text-right">Width (s)</th><th class="px-2 py-1 text-right">RA (°)</th>
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
              <td class="px-2 py-1 text-right">{{ c.ra.toFixed(2) }}</td>
              <td class="px-2 py-1 text-right">{{ c.dec.toFixed(2) }}</td>
              <td class="px-2 py-1 text-right">{{ c.el.toFixed(0) }}</td>
              <td class="px-2 py-1"><UBadge :color="clsColor[c.cls]" variant="subtle" size="xs" :label="clsLabel[c.cls] ?? c.cls" /></td>
              <td class="px-2 py-1"><UButton size="2xs" variant="outline" label="Spectrogram" @click="showCandidate(c)" /></td>
            </tr>
            <tr v-if="!shownCands.length && !candsPending"><td colspan="10" class="px-2 py-3 text-center text-gray-500">No candidates in this period.</td></tr>
          </tbody>
        </table>
      </div>
    </UCard>

    <UCard :ui="{ body: { padding: 'p-2 sm:p-3' } }">
      <template #header>
        <div class="flex flex-wrap items-center gap-3">
          <span class="font-medium">Spectrogram of a position</span>
          <UInput v-model="raInput" placeholder="RA (°)" size="xs" class="w-28" @keyup.enter="showPosition" />
          <UInput v-model="decInput" placeholder="Dec (°)" size="xs" class="w-28" @keyup.enter="showPosition" />
          <USelect v-model="hours" :options="[1, 2, 3, 6].map(h => ({ label: `last ${h} h`, value: h }))" size="xs" />
          <UButton size="xs" variant="outline" label="Display" :disabled="!!positionError || raInput === '' || decInput === ''" @click="showPosition" />
          <span v-if="positionError" class="text-xs text-red-500">{{ positionError }}</span>
        </div>
      </template>
      <SpectrogramSkymonPixel v-if="ra != null && dec != null" :ra="ra" :dec="dec" :hours="hours" :t-inf="mark?.tInf" :dm="mark?.dm" />
      <p v-else class="text-center text-gray-500 dark:text-gray-400 py-6">
        Enter a position, or open the spectrogram of a candidate. Each monitor keeps the spectrum of every tracked position, averaged over 10 s, for the last six hours.
      </p>
    </UCard>
  </UDashboardPanelContent>
</template>
