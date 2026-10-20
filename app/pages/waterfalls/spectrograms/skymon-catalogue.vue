<script setup lang="ts">
// The catalogue of the all-sky monitor: every FRB event, each opening into its
// detections in the bands, and every giant pulse, from the head database. The
// archived data of each detection can be downloaded by anyone 30 days after
// detection, and by a logged-in team member at once.
const rtConfig = useRuntimeConfig()
const tz = useTimeZone()
const route = useRoute()
const router = useRouter()

interface Det {
  node: string, id: string, kind: string, event_id: string | null, state: string | null, pulsar: string | null,
  t_inf: number, f_lo_mhz: number | null, f_hi_mhz: number | null, snr: number | null, dm: number | null,
  width_s: number | null, fluence_jy_ms: number | null, ra: number | null, dec: number | null, el: number | null,
  available_from: number, archived: boolean
}
interface Ev {
  id: string, status: string, review: string | null, t_inf: number, ra: number | null, dec: number | null,
  dm: number | null, dm_err: number | null, snr: number | null, n_seen: number | null, n_could_see: number | null,
  reviews: { verdict: string, by: string, note: string, at: number }[], disturbed: boolean,
  spectrum?: { consistent_with?: string[] } | null, available_from: number, detections: Det[]
}

const kind = ref<'frb' | 'giant_pulse'>(route.query.kind == 'giant_pulse' ? 'giant_pulse' : 'frb')
const sinceDays = ref(Number(route.query.days) || 30)
// 'any' for no filter (a select item cannot have an empty value)
const status = ref<string>(typeof route.query.status == 'string' ? route.query.status : 'any')
const review = ref<string>(typeof route.query.review == 'string' ? route.query.review : 'any')
const page = ref(Number(route.query.page) || 1)
const pageSize = 50

const rows = ref<(Ev | Det)[]>([])
const count = ref(0)
const pending = ref(true)
const error = ref('')
async function load() {
  pending.value = true
  error.value = ''
  try {
    const q: Record<string, any> = { kind: kind.value, since_days: sinceDays.value, limit: pageSize, offset: (page.value - 1) * pageSize }
    if (kind.value == 'frb' && status.value != 'any') q.status = status.value
    if (kind.value == 'frb' && review.value != 'any') q.review = review.value
    const r = await $fetch<{ count: number, rows: (Ev | Det)[] }>(rtConfig.public.fastapiBase + '/skymon/catalogue', { query: q })
    rows.value = r.rows
    count.value = r.count
  } catch (e: any) {
    rows.value = []
    count.value = 0
    error.value = e?.statusCode == 503 ? 'The catalogue is not available.' : 'The catalogue could not be loaded.'
  } finally {
    pending.value = false
  }
}
watch([kind, sinceDays, status, review], () => { page.value = 1; expanded.value = null; load() })
watch(page, load)
watch([kind, sinceDays, status, review, page], () => {
  const q: Record<string, string> = {}
  if (kind.value != 'frb') q.kind = kind.value
  if (sinceDays.value != 30) q.days = String(sinceDays.value)
  if (status.value != 'any') q.status = status.value
  if (review.value != 'any') q.review = review.value
  if (page.value > 1) q.page = String(page.value)
  router.replace({ query: q })
})

const expanded = ref<string | null>(null)
const events = computed(() => kind.value == 'frb' ? rows.value as Ev[] : [])
const pulses = computed(() => kind.value == 'giant_pulse' ? rows.value as Det[] : [])

// downloads: open to all after the lock, to a logged-in team member at once (the server checks)
const hanko = useHanko()
const loggedIn = ref(false)
const now = ref(Date.now() / 1000)
const canDownload = (d: Det) => now.value >= d.available_from || loggedIn.value
const dataUrl = (d: Det, ext: string) => `${rtConfig.public.fastapiBase}/skymon/catalogue/data/${encodeURIComponent(d.node)}/${encodeURIComponent(d.id)}.${ext}`

const kinds = [{ label: 'FRB events', value: 'frb' }, { label: 'Giant pulses', value: 'giant_pulse' }]
const periods = [{ label: '7 days', value: 7 }, { label: '30 days', value: 30 }, { label: '90 days', value: 90 },
  { label: '1 year', value: 365 }, { label: 'All', value: 3650 }]
const statuses = [{ label: 'Any result', value: 'any' }, { label: 'Confirmed', value: 'confirmed' },
  { label: 'One band, plausible spectrum', value: 'band_limited' }, { label: 'One band, implausible spectrum', value: 'implausible' },
  { label: 'Single band only', value: 'unconfirmable' }, { label: 'Pending', value: 'pending' }]
const reviews = [{ label: 'Any review', value: 'any' }, { label: 'Needs review', value: 'pending' }, { label: 'FRB', value: 'frb' },
  { label: 'RFI', value: 'rfi' }, { label: 'Unclear', value: 'unclear' }]
const statusLabel: Record<string, string> = Object.fromEntries(statuses.filter(s => s.value != 'any').map(s => [s.value, s.label]))
const statusColor: Record<string, string> = { pending: 'info', confirmed: 'success', band_limited: 'warning', implausible: 'neutral', unconfirmable: 'neutral' }
const reviewLabel: Record<string, string> = { pending: 'Needs review', frb: 'FRB', rfi: 'RFI', unclear: 'Unclear' }
const stateLabel: Record<string, string> = { detected: 'detected', followup: 'measured' }

const band = (d: Det) => d.f_lo_mhz != null && d.f_hi_mhz != null ? `${d.f_lo_mhz.toFixed(2)}–${d.f_hi_mhz.toFixed(2)}` : ''
const fmt = (x: number | null | undefined, n = 1) => x == null ? '' : x.toFixed(n)
const fluence = (f: number | null) => f == null ? '' : f >= 1000 ? `${(f / 1000).toFixed(1)} Jy s` : `${f.toPrecision(3)} Jy ms`
const day = (t: number) => tz.dateTime(t * 1000).slice(0, 10)

// the table's look, as the site's other tables (Nuxt UI's UTable)
const th = 'text-left px-4 py-3.5 text-gray-900 dark:text-white font-semibold text-sm whitespace-nowrap'
const td = 'whitespace-nowrap px-4 py-3 text-gray-500 dark:text-gray-400 text-sm'

onMounted(() => {
  tz.restore()
  hanko?.validateSession().then(r => { loggedIn.value = r.is_valid }).catch(() => { loggedIn.value = false })
  load()
})

useSeoMeta({
  title: 'All-sky monitor catalogue @ LWA-Sevilleta',
  ogTitle: 'All-sky monitor catalogue @ LWA-Sevilleta',
  description: 'The FRB events and giant pulses found by the all-sky monitor of the EPIC imager at the Long Wavelength Array in Sevilleta, with their data.',
  ogDescription: 'The FRB events and giant pulses found by the all-sky monitor of the EPIC imager at the Long Wavelength Array in Sevilleta, with their data.'
})
</script>

<template>
  <UDashboardPanel id="skymon-catalogue">
    <template #header>
      <PageToolbar>
        <span class="text-sm text-gray-500 dark:text-gray-400">All-sky monitor catalogue</span>
        <USelect v-model="kind" :items="kinds" size="xs" />
        <USelect v-model="sinceDays" :items="periods" size="xs" />
        <template v-if="kind == 'frb'">
          <USelect v-model="status" :items="statuses" size="xs" />
          <USelect v-model="review" :items="reviews" size="xs" />
        </template>
        <template #right><TimeZoneToggle /></template>
      </PageToolbar>
    </template>
    <template #body>
        <UCard :ui="{ body: 'p-0 sm:p-0' }">
          <UProgress v-if="pending" animation="carousel" size="xs" />
          <div v-if="error" class="p-3"><UAlert color="error" variant="soft" icon="i-heroicons-exclamation-triangle" :title="error" /></div>
          <div class="overflow-x-auto">
            <!-- FRB events, each opening into its detections -->
            <table v-if="kind == 'frb'" class="min-w-full table-fixed divide-y divide-gray-300 dark:divide-gray-700">
              <thead>
                <tr>
                  <th :class="th">Arrival ({{ tz.zoneName() }})</th><th :class="th">Result</th><th :class="th">Review</th>
                  <th :class="[th, 'text-right']">DM (pc cm⁻³)</th><th :class="[th, 'text-right']">S/N</th>
                  <th :class="[th, 'text-right']">RA (°)</th><th :class="[th, 'text-right']">Dec (°)</th>
                  <th :class="th">Bands</th><th :class="th">Data</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200 dark:divide-gray-800">
                <template v-for="e in events" :key="e.id">
                  <tr class="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
                    :class="expanded == e.id ? 'bg-primary-50 dark:bg-primary-400/15' : ''"
                    @click="expanded = expanded == e.id ? null : e.id">
                    <td :class="[td, 'font-mono text-gray-900 dark:text-white']">
                      <UIcon :name="expanded == e.id ? 'i-heroicons-chevron-down-20-solid' : 'i-heroicons-chevron-right-20-solid'" class="w-4 h-4 align-middle" />
                      {{ tz.dateTime(e.t_inf * 1000) }}
                    </td>
                    <td :class="td"><UBadge :color="statusColor[e.status] ?? 'neutral'" variant="soft" size="md" :label="statusLabel[e.status] ?? e.status" class="!text-[10px] !px-1 !py-0 leading-4 whitespace-nowrap" /></td>
                    <td :class="td">
                      <UBadge v-if="e.review" :color="e.review == 'pending' ? 'notice' : e.review == 'frb' ? 'success' : 'neutral'" variant="outline" size="md" :label="reviewLabel[e.review] ?? e.review" class="!text-[10px] !px-1 !py-0 leading-4 whitespace-nowrap" />
                    </td>
                    <td :class="[td, 'text-right tabular-nums']">{{ e.dm != null ? `${e.dm.toFixed(1)} ± ${fmt(e.dm_err)}` : '' }}</td>
                    <td :class="[td, 'text-right tabular-nums']">{{ fmt(e.snr) }}</td>
                    <td :class="[td, 'text-right tabular-nums']">{{ fmt(e.ra, 2) }}</td>
                    <td :class="[td, 'text-right tabular-nums']">{{ fmt(e.dec, 2) }}</td>
                    <td :class="td">{{ e.n_seen != null ? `${e.n_seen} of ${e.n_could_see ?? e.n_seen}` : '' }}</td>
                    <td :class="td">{{ now >= e.available_from ? 'open' : `from ${day(e.available_from)}` }}</td>
                  </tr>
                  <template v-if="expanded == e.id">
                    <tr class="bg-gray-50 dark:bg-gray-800/40">
                      <td colspan="9" class="pl-12 pr-4 py-2">
                        <table v-if="e.detections.length" class="min-w-full">
                          <thead>
                            <tr class="text-xs text-gray-500 dark:text-gray-400">
                              <th class="text-left font-medium px-3 py-1">Band (MHz)</th><th class="text-left font-medium px-3 py-1">How</th>
                              <th class="text-right font-medium px-3 py-1">DM (pc cm⁻³)</th><th class="text-right font-medium px-3 py-1">S/N</th>
                              <th class="text-right font-medium px-3 py-1">Width</th><th class="text-right font-medium px-3 py-1">Fluence</th>
                              <th class="text-left font-medium px-3 py-1">Data</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="d in e.detections" :key="d.node + d.id" class="text-sm text-gray-600 dark:text-gray-300">
                              <td class="px-3 py-1 whitespace-nowrap tabular-nums">{{ band(d) }}</td>
                              <td class="px-3 py-1">{{ stateLabel[d.state ?? ''] ?? d.state }}</td>
                              <td class="px-3 py-1 text-right tabular-nums">{{ fmt(d.dm) }}</td>
                              <td class="px-3 py-1 text-right tabular-nums">{{ fmt(d.snr) }}</td>
                              <td class="px-3 py-1 text-right tabular-nums">{{ d.width_s != null ? `${fmt(d.width_s, 2)} s` : '' }}</td>
                              <td class="px-3 py-1 text-right tabular-nums">{{ fluence(d.fluence_jy_ms) }}</td>
                              <td class="px-3 py-1 whitespace-nowrap">
                                <template v-if="!d.archived">not archived yet</template>
                                <template v-else-if="canDownload(d)">
                                  <a :href="dataUrl(d, 'npz')" class="text-primary-500 hover:underline" download>data</a>
                                  <a :href="dataUrl(d, 'json')" class="ml-3 text-primary-500 hover:underline" download>record</a>
                                </template>
                                <template v-else>from {{ day(d.available_from) }}</template>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                        <span v-else class="text-sm text-gray-500 dark:text-gray-400">No detection catalogued.</span>
                      </td>
                    </tr>
                    <tr v-if="e.reviews?.length || e.spectrum?.consistent_with?.length" class="bg-gray-50 dark:bg-gray-800/40">
                      <td colspan="9" class="px-12 py-2 text-xs text-gray-500 dark:text-gray-400 space-y-0.5">
                        <div v-if="e.spectrum?.consistent_with?.length">The S/N measured in the bands is consistent with {{ e.spectrum.consistent_with.join(', or with ') }}.</div>
                        <div v-for="(r, i) in e.reviews" :key="i">
                          {{ tz.dateTime(r.at * 1000) }}, {{ r.by }} reviewed it as {{ reviewLabel[r.verdict] ?? r.verdict }}<template v-if="r.note">. {{ r.note }}</template>
                        </div>
                      </td>
                    </tr>
                  </template>
                </template>
                <tr v-if="!events.length && !pending"><td colspan="9" :class="[td, 'text-center py-6']">No FRB events in this period.</td></tr>
              </tbody>
            </table>

            <!-- giant pulses -->
            <table v-else class="min-w-full table-fixed divide-y divide-gray-300 dark:divide-gray-700">
              <thead>
                <tr>
                  <th :class="th">Arrival ({{ tz.zoneName() }})</th><th :class="th">Pulsar</th><th :class="th">Band (MHz)</th>
                  <th :class="[th, 'text-right']">S/N</th><th :class="[th, 'text-right']">DM (pc cm⁻³)</th>
                  <th :class="[th, 'text-right']">Width</th><th :class="[th, 'text-right']">Fluence</th><th :class="th">Data</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200 dark:divide-gray-800">
                <tr v-for="d in pulses" :key="d.node + d.id">
                  <td :class="[td, 'font-mono text-gray-900 dark:text-white']">{{ tz.dateTime(d.t_inf * 1000) }}</td>
                  <td :class="td"><SpectrogramSkymonPulsarName v-if="d.pulsar" :name="d.pulsar" :size="22" /></td>
                  <td :class="td">{{ band(d) }}</td>
                  <td :class="[td, 'text-right tabular-nums']">{{ fmt(d.snr) }}</td>
                  <td :class="[td, 'text-right tabular-nums']">{{ fmt(d.dm) }}</td>
                  <td :class="[td, 'text-right tabular-nums']">{{ fmt(d.width_s, 2) }} s</td>
                  <td :class="[td, 'text-right tabular-nums']">{{ fluence(d.fluence_jy_ms) }}</td>
                  <td :class="td">
                    <template v-if="!d.archived">not archived yet</template>
                    <template v-else-if="canDownload(d)">
                      <a :href="dataUrl(d, 'npz')" class="text-primary-500 hover:underline" download>data</a>
                      <a :href="dataUrl(d, 'json')" class="ml-3 text-primary-500 hover:underline" download>record</a>
                    </template>
                    <template v-else>from {{ day(d.available_from) }}</template>
                  </td>
                </tr>
                <tr v-if="!pulses.length && !pending"><td colspan="8" :class="[td, 'text-center py-6']">No giant pulses in this period.</td></tr>
              </tbody>
            </table>
          </div>
          <div v-if="count > pageSize" class="flex justify-end px-3 py-3 border-t border-gray-200 dark:border-gray-700">
            <UPagination v-model:page="page" :items-per-page="pageSize" :total="count" />
          </div>
        </UCard>
    </template>
  </UDashboardPanel>
</template>
