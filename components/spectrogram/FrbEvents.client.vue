<script setup lang="ts">
import Plotly from 'plotly.js-dist-min'

// Dedispersed view of a CHIME/FRB watch across every imaging band. Each
// channel is shifted by its dispersion delay at the CHIME DM, so a burst at
// that DM sits at 0 s in every channel and band. Products are precomputed by
// the backend when a watch ends.

interface FrbEventItem {
  id: number, source: string, event_time: string, t_ref: string | null, f_ref_mhz: number, t_start: string, t_end: string,
  watch_status: string, n_bands: number, max_snr: number | null, computed_at: string | null,
  dm: number | null, dm_err: number | null
}
interface FrbEventPage { data: FrbEventItem[], count: number }
interface FrbBand {
  chan0: number, status: string, note: string | null, f_lo_mhz: number, chan_bw_hz: number,
  n_chan: number, dt_s: number, t0_rel_s: number, n_time: number, smear_s: number,
  on_half_s: number, coverage: number | null, flagged: number[] | null, z_image: string | null,
  timeseries: string | null, peak_snr: number | null, peak_width_s: number | null,
  peak_t_s: number | null, created_at: string
}
interface FrbEventProducts {
  id: number, source: string, t_inf: string, t_ref: string, f_ref_mhz: number, t_start: string, t_end: string,
  dm: number, dm_err: number, computed: boolean, bands: FrbBand[]
}

const rtConfig = useRuntimeConfig()
const route = useRoute()
const router = useRouter()
const colorMode = useColorMode()
const dark = computed(() => colorMode.value == 'dark')

const K_DM = 4148.808
const tz = useTimeZone()

// Events a page at a time, sorted by the server. Without a sort column the
// most recent trigger comes first.
// A calendar day, in the chosen time zone, lists only the events triggered
// that day; days with an event carry a dot, as on the LWA-SV watch list
const eventDay = ref<string | null>(null)
const eventDayRange = computed(() => eventDay.value ? tz.dayRange(eventDay.value) : null)
const markRange = ref<[string, string] | null>(null)
const { data: eventTimes } = await useLazyAsyncData<{ time: string }[]>('frb-event-days', () => markRange.value
  ? $fetch(rtConfig.public.fastapiBase + '/watchlist/events/', {
    query: { start: tz.dayRange(markRange.value[0])[0] + 'Z', end: tz.dayRange(markRange.value[1])[1] + 'Z', category: 'frb' }
  })
  : Promise.resolve([]), { watch: [markRange, tz.mode], default: () => [], server: false })
const eventDays = computed(() => {
  const out: Record<string, number> = {}
  for (const e of eventTimes.value ?? []) { const k = tz.dayKey(e.time); out[k] = (out[k] ?? 0) + 1 }
  return out
})

const page = ref(1)
const rowsPerPage = ref(10)
const availRowsPerPage = [5, 10, 25]
const sort = ref<{ column: string, direction: 'asc' | 'desc' }>({ column: '', direction: 'asc' })
const { data: events, pending: eventsPending } = await useLazyAsyncData<FrbEventPage>(
  'frb-events',
  () => $fetch(rtConfig.public.fastapiBase + '/frb/events/', {
    query: {
      page: page.value, nrows: rowsPerPage.value, sort: sort.value.column || undefined, order: sort.value.direction,
      start: eventDayRange.value ? eventDayRange.value[0] + 'Z' : undefined,
      end: eventDayRange.value ? eventDayRange.value[1] + 'Z' : undefined
    }
  }),
  { watch: [page, rowsPerPage, sort, eventDayRange], default: () => ({ data: [], count: 0 }) })
watch([rowsPerPage, sort, eventDayRange], () => { page.value = 1 })
const pageTotal = computed(() => events.value.count)
const pageFrom = computed(() => Math.min((page.value - 1) * rowsPerPage.value + 1, pageTotal.value))
const pageTo = computed(() => Math.min(page.value * rowsPerPage.value, pageTotal.value))

// Nothing is shown until an event is chosen, from the table or a link
const selectedId = ref<number | null>(Number(route.query.event) || null)
// Two tabs as on the LWA-SV page: the event list, and the analysis of the
// selected event. A link with ?event= opens on the analysis.
const tabItems = [
  { label: 'Event', icon: 'i-material-symbols-view-list', slot: 'events' },
  { label: 'Analysis', icon: 'i-material-symbols-key-visualizer', slot: 'analysis' }
]
const tabIndex = ref(route.query.tab != null ? (Number(route.query.tab) ? 1 : 0) : (selectedId.value ? 1 : 0))
function pickEvent(row: FrbEventItem) {
  selectedId.value = row.id
  tabIndex.value = 1 // also when the same event is clicked again
}
watch([selectedId, tabIndex], ([id, tab]) => router.replace({ query: { ...route.query, event: id ?? undefined, tab: String(tab) } }))

const { data: product, pending: productPending } = await useLazyAsyncData<FrbEventProducts | null>(
  'frb-event',
  () => selectedId.value ? $fetch(rtConfig.public.fastapiBase + `/frb/events/${selectedId.value}`) : Promise.resolve(null),
  { watch: [selectedId], default: () => null }
)

const eventRows = computed(() => (events.value?.data ?? []).map(e => ({
  ...e,
  dm_text: e.dm != null ? `${e.dm.toFixed(1)} ± ${(e.dm_err ?? 0).toFixed(1)}` : '',
  snr_text: e.max_snr != null ? e.max_snr.toFixed(1) : '',
  products: e.computed_at ? (e.n_bands ? `${e.n_bands} band${e.n_bands == 1 ? '' : 's'}` : 'No data') : (e.watch_status == 'watching' ? 'Active' : 'Pending'),
  class: e.id == selectedId.value ? 'bg-primary-50 dark:bg-primary-900/30' : ''
})))
const eventColumns = computed(() => [
  { key: 'source', label: 'Event', sortable: true },
  { key: 't_ref', label: `Burst at 400 MHz (${tz.zoneName()})`, sortable: true },
  { key: 'event_time', label: `Trigger (${tz.zoneName()})`, sortable: true },
  { key: 'dm_text', label: 'DM (pc cm⁻³)', sortable: true },
  { key: 'products', label: 'Products', sortable: true },
  { key: 'snr_text', label: 'Peak S/N', sortable: true }
])

function b64ToF32(b64: string) {
  const bin = atob(b64)
  const u8 = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i)
  return new Float32Array(u8.buffer)
}

const timeText = (t: string | Date) => `${tz.dateTime(t)} ${tz.zoneName(t)}`
const bandRange = (b: FrbBand) => `${(b.f_lo_mhz + b.n_chan * b.chan_bw_hz / 1e6).toFixed(2)}–${b.f_lo_mhz.toFixed(2)} MHz`

// Bands with data, highest frequency first, decoded once
const bands = computed(() => {
  const p = product.value
  if (!p) return []
  return p.bands.filter(b => b.status == 'ok' && b.z_image && b.timeseries).map(b => {
    const img = b64ToF32(b.z_image!)
    const rel = Array.from({ length: b.n_time }, (_, k) => b.t0_rel_s + k * b.dt_s)
    const freqs = Array.from({ length: b.n_chan }, (_, c) => b.f_lo_mhz + (c + 0.5) * b.chan_bw_hz / 1e6)
    const z = Array.from({ length: b.n_chan }, (_, c) => Array.from(img.subarray(c * b.n_time, (c + 1) * b.n_time)))
    return { ...b, rel, freqs, z, ts: b64ToF32(b.timeseries!) }
  }).sort((a, b) => b.f_lo_mhz - a.f_lo_mhz)
})

const summary = computed(() => {
  const p = product.value
  if (!p) return []
  return [...p.bands].sort((a, b) => b.f_lo_mhz - a.f_lo_mhz).map(b => {
    const fMid = b.f_lo_mhz + b.n_chan * b.chan_bw_hz / 2e6
    const arrival = new Date(new Date(p.t_inf + 'Z').getTime() + 1e3 * K_DM * p.dm / fMid ** 2)
    return {
      band: bandRange(b),
      arrival: tz.clock(arrival),
      smear: b.smear_s != null ? `${b.smear_s.toFixed(1)} s` : '',
      coverage: b.status == 'ok' && b.coverage != null ? `${Math.round(100 * b.coverage)}%` : '',
      flagged: b.status == 'ok' ? `${b.flagged?.length ?? 0} / ${b.n_chan}` : '',
      peak: b.peak_snr != null ? `${b.peak_snr.toFixed(1)} at ${b.peak_t_s!.toFixed(1)} s, ${b.peak_width_s!.toFixed(2)} s wide` : '',
      status: b.status == 'ok' ? 'Data' : (b.note ?? b.status)
    }
  })
})
const summaryColumns = computed(() => [
  { key: 'band', label: 'Band' },
  { key: 'arrival', label: `Expected arrival (${tz.zoneName()})` },
  { key: 'smear', label: 'Smearing' },
  { key: 'coverage', label: 'Coverage' },
  { key: 'flagged', label: 'Flagged channels' },
  { key: 'peak', label: 'Peak S/N (search window)' },
  { key: 'status', label: 'Status' }
])

// Display controls
const zMax = ref(5)
const zMaxOptions = [{ label: 'S/N −2 to 3', value: 3 }, { label: 'S/N −2 to 5', value: 5 }, { label: 'S/N −2 to 8', value: 8 }]
const smoothS = ref(0)
const smoothOptions = [{ label: 'None', value: 0 }, { label: '0.5 s', value: 0.5 }, { label: '1 s', value: 1 }, { label: '4 s', value: 4 }, { label: '16 s', value: 16 }]
const zoomS = ref(0)
const zoomOptions = [{ label: 'Full window', value: 0 }, { label: '±60 s', value: 60 }, { label: '±20 s', value: 20 }, { label: '±5 s', value: 5 }]

// Boxcar-smoothed time series, rescaled to S/N with the off-window samples
function smoothed(b: (typeof bands.value)[number]) {
  const w = Math.max(1, Math.round(smoothS.value / b.dt_s))
  const n = b.ts.length
  const out = new Float32Array(n).fill(NaN)
  let sum = 0, cnt = 0
  for (let i = 0; i < n + Math.floor(w / 2); i++) {
    if (i < n && isFinite(b.ts[i])) { sum += b.ts[i]; cnt++ }
    const drop = i - w
    if (drop >= 0 && isFinite(b.ts[drop])) { sum -= b.ts[drop]; cnt-- }
    const c = i - Math.floor(w / 2)
    if (c >= 0 && c < n && cnt >= w / 2) out[c] = sum / cnt
  }
  if (w == 1) return Array.from(out)
  const off = Array.from(out).filter((v, i) => isFinite(v) && Math.abs(b.rel[i]) > b.on_half_s).sort((x, y) => x - y)
  const med = off[Math.floor(off.length / 2)] ?? 0
  const dev = off.map(v => Math.abs(v - med)).sort((x, y) => x - y)
  const sig = 1.4826 * (dev[Math.floor(dev.length / 2)] ?? 1) || 1
  return Array.from(out, v => (v - med) / sig)
}

const ink = computed(() => dark.value ? '#e5e7eb' : '#1f2937')
const muted = computed(() => dark.value ? '#9ca3af' : '#6b7280')
const grid = computed(() => dark.value ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)')
const paper = computed(() => dark.value ? '#131826' : '#ffffff')

// One row per band with its own axes, sharing the relative time scale
function stackedLayout(n: number, rowHeight: number, yTitle: (b: (typeof bands.value)[number]) => string, shade = false) {
  const gap = 0.35 / Math.max(n, 1) / 2
  const layout: Record<string, any> = {
    height: n * rowHeight + 90, margin: { l: 70, r: 20, t: 20, b: 60 },
    paper_bgcolor: paper.value, plot_bgcolor: paper.value, hovermode: false, showlegend: false,
    font: { family: 'Courier New, monospace', color: ink.value, size: 12 }, shapes: [], annotations: []
  }
  bands.value.forEach((b, i) => {
    const s = i == 0 ? '' : String(i + 1)
    const top = 1 - i / n
    const halfX = zoomS.value || -b.rel[0]
    layout[`xaxis${s}`] = {
      anchor: `y${s}`, range: [-halfX, halfX], gridcolor: grid.value, zeroline: false,
      showticklabels: true, tickfont: { color: muted.value },
      title: i == n - 1 ? { text: 'Time relative to the dispersed arrival (s)', font: { color: ink.value } } : undefined
    }
    layout[`yaxis${s}`] = {
      anchor: `x${s}`, domain: [top - 1 / n + gap, top - gap], gridcolor: grid.value, zeroline: false,
      tickfont: { color: muted.value }, title: { text: yTitle(b), font: { color: muted.value, size: 11 } }
    }
    layout.annotations.push({
      xref: 'paper', yref: 'paper', x: 0, y: top - gap, xanchor: 'left', yanchor: 'bottom', showarrow: false,
      text: `${bandRange(b)} · smearing ${b.smear_s.toFixed(1)} s`, font: { color: ink.value, size: 12 }
    })
    // the search window: shaded behind a time series, outlined over an image
    if (shade) {
      layout.shapes.push({
        type: 'rect', xref: `x${s}`, yref: `y${s} domain`, x0: -b.on_half_s, x1: b.on_half_s, y0: 0, y1: 1,
        fillcolor: 'rgba(245,158,11,0.14)', line: { width: 0 }, layer: 'below'
      })
    } else {
      for (const x of [-b.on_half_s, b.on_half_s]) {
        layout.shapes.push({
          type: 'line', xref: `x${s}`, yref: `y${s} domain`, x0: x, x1: x, y0: 0, y1: 1,
          line: { color: dark.value ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.7)', width: 1.5, dash: 'dash' }
        })
      }
    }
  })
  return layout
}

const imageDiv = ref<HTMLElement>()
const seriesDiv = ref<HTMLElement>()

function drawImage() {
  const el = imageDiv.value
  if (!el || !el.clientWidth || !bands.value.length) return
  const traces = bands.value.map((b, i) => ({
    type: 'heatmap', x: b.rel, y: b.freqs, z: b.z, coloraxis: 'coloraxis',
    xaxis: `x${i == 0 ? '' : i + 1}`, yaxis: `y${i == 0 ? '' : i + 1}`, hoverongaps: false
  }))
  const layout = stackedLayout(bands.value.length, 170, () => 'MHz')
  layout.coloraxis = {
    colorscale: 'Viridis', cmin: -2, cmax: zMax.value,
    colorbar: { title: { text: 'S/N', side: 'right', font: { color: ink.value } }, tickfont: { color: muted.value }, thickness: 12, len: 0.6 }
  }
  Plotly.react(el, traces, layout, { displaylogo: false, responsive: true })
}

function drawSeries() {
  const el = seriesDiv.value
  if (!el || !el.clientWidth || !bands.value.length) return
  const traces: any[] = []
  bands.value.forEach((b, i) => {
    const s = i == 0 ? '' : String(i + 1)
    traces.push({
      type: 'scatter', mode: 'lines', x: b.rel, y: smoothed(b), xaxis: `x${s}`, yaxis: `y${s}`,
      line: { width: 1, color: dark.value ? '#93c5fd' : '#1d4ed8' }
    })
    if (b.peak_snr != null && b.peak_t_s != null) {
      traces.push({
        type: 'scatter', mode: 'markers', x: [b.peak_t_s], y: [b.peak_snr], xaxis: `x${s}`, yaxis: `y${s}`,
        marker: { size: 9, color: '#f59e0b', line: { width: 2, color: paper.value } }
      })
    }
  })
  const layout = stackedLayout(bands.value.length, 120, () => 'S/N', true)
  bands.value.forEach((b, i) => {
    if (b.peak_snr == null) return
    layout.annotations.push({
      xref: 'paper', yref: 'paper', x: 1, y: 1 - i / bands.value.length - 0.35 / bands.value.length / 2,
      xanchor: 'right', yanchor: 'bottom', showarrow: false, font: { color: muted.value, size: 11 },
      text: `best boxcar S/N ${b.peak_snr.toFixed(1)} at ${b.peak_t_s!.toFixed(1)} s`
    })
  })
  Plotly.react(el, traces, layout, { displaylogo: false, responsive: true })
}

function drawAll() {
  drawImage()
  drawSeries()
}

watch([bands, zMax, zoomS, dark], drawImage)
watch([bands, smoothS, zoomS, dark], drawSeries)

// The divs are created after this client-only component mounts, so observe
// them when they appear and draw once they have a width
const observer = import.meta.client ? new ResizeObserver(() => drawAll()) : null
watch([imageDiv, seriesDiv], (els, old) => {
  old?.forEach(e => e && observer?.unobserve(e))
  els.forEach(e => e && observer?.observe(e))
}, { immediate: true })
onBeforeUnmount(() => observer?.disconnect())

const noDataBands = computed(() => (product.value?.bands ?? []).filter(b => b.status != 'ok'))
</script>

<template>
  <!-- the sidebar names the page; the bar stays only on small screens, for the menu button -->
  <UDashboardNavbar class="lg:hidden" title="FRB events" />
  <UDashboardPanelContent>
    <UTabs :items="tabItems" v-model="tabIndex">
      <template #default="{ item, index, selected }">
        <div class="flex items-center gap-2 relative truncate">
          <UIcon :name="item.icon" class="w-4 h-4 flex-shrink-0" />
          <span class="truncate">{{ index + 1 }}. {{ item.label }}</span>
          <span v-if="selected" class="absolute -right-4 w-2 h-2 rounded-full bg-primary-500 dark:bg-primary-400" />
        </div>
      </template>
      <template #events>
    <div>
    <UCard :ui="{ body: { padding: 'px-2 py-2 sm:p-3' } }" class="relative mt-2">
      <UProgress v-if="eventsPending" animation="elastic" size="xs" class="p-0 m-0 top-0 left-0 absolute" />
      <div class="flex flex-wrap justify-between items-center gap-3 px-1 pb-2">
        <div class="flex items-center gap-1.5">
          <span class="text-sm leading-5">Rows per page</span>
          <USelect v-model="rowsPerPage" :options="availRowsPerPage" />
          <SpectrogramDayPicker v-model="eventDay" :marks="eventDays" class="ml-2" @range="(a, b) => markRange = [a, b]">
            <template #legend>
              <span class="flex items-center gap-1.5"><span class="h-1.5 w-1.5 rounded-full bg-amber-500 dark:bg-amber-400" />CHIME/FRB event</span>
            </template>
          </SpectrogramDayPicker>
        </div>
        <div class="flex items-center gap-3">
          <UButton v-if="sort.column" size="xs" color="gray" variant="ghost" icon="i-heroicons-arrow-uturn-left"
            label="Default order" @click="sort = { column: '', direction: 'asc' }" />
          <TimeZoneToggle />
        </div>
      </div>
      <UTable :rows="eventRows" :columns="eventColumns" :loading="eventsPending" v-model:sort="sort" sort-mode="manual"
        :empty-state="{ icon: 'i-heroicons-circle-stack-20-solid', label: 'No CHIME/FRB events have been watched.' }"
        @select="pickEvent">
        <template #t_ref-data="{ row }">{{ row.t_ref ? tz.dateTime(row.t_ref) : '' }}</template>
        <template #event_time-data="{ row }">{{ tz.dateTime(row.event_time) }}</template>
      </UTable>
      <div class="flex justify-between flex-wrap items-center gap-2 px-1 pt-3 border-t border-gray-200 dark:border-gray-700">
        <span class="text-sm leading-5">
          Showing <span class="font-medium">{{ pageFrom }}</span> to <span class="font-medium">{{ pageTo }}</span>
          of <span class="font-medium">{{ pageTotal }}</span> events
        </span>
        <UPagination v-if="pageTotal > rowsPerPage" v-model="page" :page-count="rowsPerPage" :total="pageTotal" :ui="{
          wrapper: 'flex items-center gap-1',
          rounded: '!rounded-full min-w-[32px] justify-center',
          default: { activeButton: { variant: 'outline' } }
        }" />
      </div>
    </UCard>

    </div>
      </template>
      <template #analysis>
    <!-- The blocks all appear when the event's data arrive, and inside the tab
         panel Vue inserted the DM transform ahead of the others; a fixed CSS
         order keeps them in reading order whatever the DOM order -->
    <div class="flex flex-col">
    <UCard v-if="!selectedId" :ui="{ body: { padding: 'px-4 py-10' } }" class="mt-2 order-1">
      <div class="flex flex-col items-center gap-2 text-center text-gray-500 dark:text-gray-400">
        <UIcon name="i-heroicons-cursor-arrow-rays" class="w-8 h-8" />
        <p class="text-base">Select an event in the Event tab to see its analysis.</p>
      </div>
    </UCard>

    <UCard v-if="product" :ui="{ body: { padding: 'px-3 py-3 sm:p-4' } }" class="mt-2 relative order-2">
      <UProgress v-if="productPending" animation="elastic" size="xs" class="p-0 m-0 top-0 left-0 absolute" />
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-xl font-semibold">{{ product.source }}</h2>
        <span class="text-sm text-gray-500 dark:text-gray-400">
          DM {{ product.dm.toFixed(2) }} ± {{ product.dm_err.toFixed(2) }} pc cm⁻³ ·
          burst at {{ product.f_ref_mhz }} MHz {{ timeText(product.t_ref) }} (CHIME, topocentric) ·
          observed until {{ timeText(product.t_end) }}
        </span>
      </div>
      <p class="mt-2 text-sm text-gray-600 dark:text-gray-300">
        Every channel is shifted by its dispersion delay at the CHIME DM, so a burst at that DM lines up at 0 s in all
        channels and bands. RFI is masked and the data detrended first with the CHIME/FRB clipping and detrending chain,
        which also removes broadband signals that are not dispersed. Each channel is then expressed in S/N using the
        samples outside the search window. The search window, marked by the
        dashed lines and the shading, spans half the smearing within a channel, three times the arrival uncertainty
        from the DM error, and a further 2 s. Channels dominated by RFI are blanked. The imager averages its 128
        channels per band in pairs before storing the pixels, so each band is analysed as 64 channels of 47.85 kHz.
      </p>
      <UTable :rows="summary" :columns="summaryColumns" class="mt-3" :ui="{ td: { base: 'whitespace-normal' } }" />
      <UAlert v-if="!product.computed" class="mt-3" color="amber" variant="soft" icon="i-heroicons-clock"
        title="The products of this event have not been computed yet. They are made on the imaging nodes after the watch ends." />
    </UCard>

    <template v-if="bands.length">
      <UCard :ui="{ body: { padding: 'px-3 py-2 sm:px-4' } }" class="mt-2 order-3">
        <div class="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <div class="flex items-center gap-2"><span>Window</span><USelect v-model="zoomS" :options="zoomOptions" option-attribute="label" /></div>
          <div class="flex items-center gap-2"><span>Colour range</span><USelect v-model="zMax" :options="zMaxOptions" option-attribute="label" /></div>
          <div class="flex items-center gap-2"><span>Time series smoothing</span><USelect v-model="smoothS" :options="smoothOptions" option-attribute="label" /></div>
        </div>
      </UCard>
      <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-2' } }" class="mt-2 order-3">
        <div class="px-2 pt-1 text-sm font-medium">Dedispersed spectrograms</div>
        <div ref="imageDiv" class="w-full"></div>
      </UCard>
      <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-2' } }" class="mt-2 order-3">
        <div class="px-2 pt-1 text-sm font-medium">Band-averaged time series</div>
        <div ref="seriesDiv" class="w-full"></div>
      </UCard>
    </template>
    <UCard v-else-if="product?.computed && !noDataBands.length" class="mt-2 order-3">No band has data for this event.</UCard>
    <SpectrogramFrbDmt v-if="product && selectedId" :event-id="selectedId" class="order-4" />
    </div>
      </template>
    </UTabs>
  </UDashboardPanelContent>
</template>
