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
watch(sinceH, loadCands)

const pct = (x?: number | null) => x == null ? '' : `${Math.round(100 * x)}%`
const fmt = (x?: number | null, d = 1) => x == null ? '' : x.toFixed(d)
const clsLabel: Record<string, string> = { candidate: 'Candidate', injection: 'Test injection', rfi: 'RFI' }
const clsColor: Record<string, string> = { candidate: 'amber', injection: 'sky', rfi: 'gray' }

// refreshed every minute while the page is open (in the browser only)
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  tz.restore()
  loadNodes()
  loadCands()
  timer = setInterval(() => { loadNodes(); loadCands() }, 60000)
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
