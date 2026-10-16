<script setup lang="ts">
import Plotly from 'plotly.js-dist-min'

// Dispersion measure transform of an FRB event: trial DMs around the CHIME
// DM for every band and every pixel of the 5x5 grid around the source
const props = defineProps<{ eventId: number }>()

interface DmtTransform {
  chan0: number, dm_lo: number, dm_step: number, n_dm: number, snr_dm: string | null,
  map_dm_step: number | null, map_n_dm: number | null, map_tau0: number | null, map_dtau: number | null,
  map_n_tau: number | null, map: string | null, peak_snr: number | null, peak_dm: number | null,
  peak_tau: number | null, peak_width_s: number | null, extra: Record<string, number> | null
}
interface DmtBand {
  chan0: number, f_lo_mhz: number, f_hi_mhz: number, status: string, note: string | null, smear_s: number | null,
  arrival_utc: string, elevation_deg?: number, snr?: number | null, dm?: number | null, tau_s?: number | null,
  width_s?: number | null, masked_frac?: number | null, sefd_jy?: number | null, fluence_limit_jyms?: number | null
}
interface DmtSummary {
  source: string, dm_chime: number, dm_err_chime: number, t_inf: string, t_ref?: string, f_ref_mhz?: number, dm_lo: number, dm_hi: number, dm_step: number,
  search_tau_s: number, snr_threshold: number, bands: DmtBand[],
  combined: { snr: number | null, dm: number | null, tau_s: number | null, n_bands: number } | null,
  localisation: { centre_snr: number | null, best_other_snr: number | null, median_other_snr: number | null, centre_is_brightest: boolean } | null,
  detected: boolean
}
interface DmtResponse {
  computed: boolean, summary?: DmtSummary, computed_at?: string, notified_at?: string | null,
  grid?: { px: number, py: number, snr: number | null, dm: number | null, tau: number | null }[],
  pixel?: { px: number, py: number }, transforms?: DmtTransform[]
}

const rtConfig = useRuntimeConfig()
const colorMode = useColorMode()
const dark = computed(() => colorMode.value == 'dark')

const pixel = ref({ px: 0, py: 0 })
watch(() => props.eventId, () => { pixel.value = { px: 0, py: 0 } })

const { data, pending } = await useLazyAsyncData<DmtResponse | null>(
  'frb-dmt',
  () => $fetch(`${rtConfig.public.fastapiBase}/frb/events/${props.eventId}/dmt`, { query: pixel.value }),
  { watch: [() => props.eventId, pixel], default: () => null }
)

function b64ToF32(b64: string) {
  const bin = atob(b64)
  const u8 = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i)
  return new Float32Array(u8.buffer)
}
const fmt = (v: number | null | undefined, digits = 1) => v == null ? '' : v.toFixed(digits)
const bandName = (b: { f_lo_mhz: number, f_hi_mhz: number }) => `${b.f_hi_mhz.toFixed(2)}–${b.f_lo_mhz.toFixed(2)} MHz`

const summary = computed(() => data.value?.summary)
// an event whose bands all lack data has an analysis record but nothing to show
const hasData = computed(() => !!summary.value?.bands?.some(b => b.status == 'ok'))

const verdict = computed(() => {
  const s = summary.value
  if (!s) return ''
  const n = s.bands.filter(b => b.status == 'ok').length
  const c = s.combined
  if (s.detected && c) {
    return `A candidate burst at S/N ${fmt(c.snr)} combining ${c.n_bands} bands, at DM ${fmt(c.dm, 2)} pc cm⁻³ and ${fmt(c.tau_s)} s from the CHIME arrival, brightest in the source pixel.`
  }
  if (!c || c.snr == null) return 'No band had data around the expected arrival.'
  const loc = s.localisation
  const where = loc?.centre_is_brightest ? 'The source pixel has the highest peak of the 5x5 grid'
    : `The source pixel is not the brightest of the 5x5 grid (best other pixel S/N ${fmt(loc?.best_other_snr)})`
  return `No burst above S/N ${s.snr_threshold} in the ${n} bands with data. Combining them, the source pixel peaks at S/N ${fmt(c.snr)} at DM ${fmt(c.dm, 2)} pc cm⁻³, ${fmt(c.tau_s)} s from the CHIME arrival. ${where}, so the peak is consistent with noise.`
})

const bandRows = computed(() => {
  const s = summary.value
  if (!s) return []
  const rows = s.bands.map(b => ({
    band: bandName(b),
    snr: b.status == 'ok' ? fmt(b.snr) : '',
    dm: b.status == 'ok' ? fmt(b.dm, 2) : '',
    ddm: b.status == 'ok' && b.dm != null ? (b.dm - s.dm_chime >= 0 ? '+' : '') + (b.dm - s.dm_chime).toFixed(2) : '',
    tau: b.status == 'ok' ? fmt(b.tau_s) : '',
    width: b.status == 'ok' ? fmt(b.width_s, 2) : '',
    masked: b.masked_frac != null ? `${Math.round(100 * b.masked_frac)}%` : '',
    elevation: b.elevation_deg != null ? fmt(b.elevation_deg) : '',
    fluence: b.fluence_limit_jyms != null ? Math.round(b.fluence_limit_jyms).toLocaleString('en-US') : '',
    note: b.status == 'ok' ? '' : (b.note ?? '')
  }))
  const c = s.combined
  if (c) {
    rows.push({
      band: `All ${c.n_bands} bands`, snr: fmt(c.snr), dm: fmt(c.dm, 2),
      ddm: c.dm != null ? (c.dm - s.dm_chime >= 0 ? '+' : '') + (c.dm - s.dm_chime).toFixed(2) : '',
      tau: fmt(c.tau_s), width: '', masked: '', elevation: '', fluence: '', note: 'Each band smoothed to its smearing'
    })
  }
  return rows
})
const bandColumns = [
  { key: 'band', label: 'Band' }, { key: 'snr', label: 'Peak S/N' }, { key: 'dm', label: 'DM (pc cm⁻³)' },
  { key: 'ddm', label: 'DM − CHIME' }, { key: 'tau', label: 'Offset from CHIME arrival (s)' },
  { key: 'width', label: 'Boxcar (s)' }, { key: 'masked', label: 'RFI masked' }, { key: 'elevation', label: 'Elevation (°)' },
  { key: 'fluence', label: 'Fluence limit, model (Jy ms)' }, { key: 'note', label: 'Note' }
]

const ink = computed(() => dark.value ? '#e5e7eb' : '#1f2937')
const muted = computed(() => dark.value ? '#9ca3af' : '#6b7280')
const grid = computed(() => dark.value ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)')
const paper = computed(() => dark.value ? '#131826' : '#ffffff')
const font = computed(() => ({ family: 'Courier New, monospace', color: ink.value, size: 12 }))
const axis = (title: string) => ({ title: { text: title, font: { color: ink.value } }, gridcolor: grid.value, zeroline: false, tickfont: { color: muted.value } })

const transforms = computed(() => (data.value?.transforms ?? []).map(t => ({
  ...t,
  curve: t.snr_dm ? Array.from(b64ToF32(t.snr_dm)) : [],
  dms: Array.from({ length: t.n_dm }, (_, i) => t.dm_lo + i * t.dm_step),
  mapRows: t.map && t.map_n_dm && t.map_n_tau
    ? Array.from({ length: t.map_n_dm }, (_, i) => Array.from(b64ToF32(t.map!).subarray(i * t.map_n_tau!, (i + 1) * t.map_n_tau!)))
    : null
})))
const combined = computed(() => transforms.value.find(t => t.chan0 == 0))
const bandTransforms = computed(() => transforms.value.filter(t => t.chan0 != 0))
const bandOf = (chan0: number) => summary.value?.bands.find(b => b.chan0 == chan0)

const gridDiv = ref<HTMLElement>()
const curveDiv = ref<HTMLElement>()
const mapDiv = ref<HTMLElement>()
const bandMapDiv = ref<HTMLElement>()
const palette = ['#60a5fa', '#34d399', '#fbbf24', '#f472b6', '#a78bfa', '#f87171']

function drawGrid() {
  const el = gridDiv.value
  const g = data.value?.grid
  if (!el || !el.clientWidth || !g?.length) return
  const z = [2, 1, 0, -1, -2].map(py => [-2, -1, 0, 1, 2].map(px => g.find(c => c.px == px && c.py == py)?.snr ?? null))
  const text = z.map(r => r.map(v => v == null ? '' : v.toFixed(1)))
  Plotly.react(el, [{
    type: 'heatmap', z, x: [-2, -1, 0, 1, 2], y: [2, 1, 0, -1, -2], text, texttemplate: '%{text}', hoverinfo: 'none',
    colorscale: 'Viridis', zmin: 0, zmax: Math.max(7, ...z.flat().filter((v): v is number => v != null)),
    colorbar: { title: { text: 'S/N', side: 'right', font: { color: ink.value } }, tickfont: { color: muted.value }, thickness: 10 },
    textfont: { color: '#ffffff' }
  }], {
    height: 300, margin: { l: 50, r: 10, t: 10, b: 45 }, paper_bgcolor: paper.value, plot_bgcolor: paper.value, font: font.value,
    xaxis: { ...axis('Pixel offset east (px)'), dtick: 1 }, yaxis: { ...axis('Pixel offset north (px)'), dtick: 1, scaleanchor: 'x' },
    shapes: [{ type: 'rect', x0: pixel.value.px - 0.5, x1: pixel.value.px + 0.5, y0: pixel.value.py - 0.5, y1: pixel.value.py + 0.5,
      line: { color: dark.value ? '#ffffff' : '#111827', width: 2 } }]
  }, { displaylogo: false, responsive: true }).then((gd: any) => {
    gd.removeAllListeners?.('plotly_click')
    gd.on('plotly_click', (ev: any) => {
      const p = ev.points?.[0]
      if (p) pixel.value = { px: Number(p.x), py: Number(p.y) }
    })
  })
}

function drawCurves() {
  const el = curveDiv.value
  const s = summary.value
  if (!el || !el.clientWidth || !s || !transforms.value.length) return
  const traces: any[] = bandTransforms.value.map((t, i) => {
    const b = bandOf(t.chan0)
    return { type: 'scatter', mode: 'lines', x: t.dms, y: t.curve, name: b ? bandName(b) : String(t.chan0),
      line: { width: 1, color: palette[i % palette.length] } }
  })
  if (combined.value) {
    traces.push({ type: 'scatter', mode: 'lines', x: combined.value.dms, y: combined.value.curve, name: 'All bands',
      line: { width: 2.5, color: ink.value } })
  }
  Plotly.react(el, traces, {
    height: 300, margin: { l: 55, r: 10, t: 10, b: 45 }, paper_bgcolor: paper.value, plot_bgcolor: paper.value, font: font.value,
    hovermode: false, xaxis: axis('Trial DM (pc cm⁻³)'), yaxis: axis('Peak S/N in search window'),
    legend: { font: { color: ink.value, size: 11 }, orientation: 'h', y: -0.25 },
    shapes: [
      { type: 'line', xref: 'x', yref: 'paper', x0: s.dm_chime, x1: s.dm_chime, y0: 0, y1: 1, line: { color: muted.value, dash: 'dash', width: 1 } },
      { type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: s.snr_threshold, y1: s.snr_threshold, line: { color: '#f59e0b', dash: 'dot', width: 1 } }
    ]
  }, { displaylogo: false, responsive: true })
}

function mapTrace(t: (typeof transforms.value)[number], xaxis = 'x', yaxis = 'y', showscale = true) {
  const taus = Array.from({ length: t.map_n_tau! }, (_, j) => t.map_tau0! + j * t.map_dtau!)
  const dms = Array.from({ length: t.map_n_dm! }, (_, i) => t.dm_lo + (i + 0.5) * t.map_dm_step! - t.dm_step / 2)
  return { type: 'heatmap', x: taus, y: dms, z: t.mapRows, xaxis, yaxis, coloraxis: 'coloraxis', hoverongaps: false, showscale }
}
const colorAxis = computed(() => ({
  colorscale: 'Viridis', cmin: -2, cmax: Math.max(5, Math.ceil(summary.value?.snr_threshold ?? 7)),
  colorbar: { title: { text: 'S/N', side: 'right', font: { color: ink.value } }, tickfont: { color: muted.value }, thickness: 12 }
}))

function drawMap() {
  const el = mapDiv.value
  const c = combined.value
  const s = summary.value
  if (!el || !el.clientWidth || !c?.mapRows || !s) return
  const traces: any[] = [mapTrace(c)]
  if (c.peak_snr != null) {
    // a detection is marked boldly; below the threshold the peak is only the
    // highest point in the search window, which noise always provides
    const detected = c.peak_snr >= s.snr_threshold
    traces.push({ type: 'scatter', mode: 'markers+text', x: [c.peak_tau], y: [c.peak_dm],
      text: [detected ? `detection, S/N ${c.peak_snr.toFixed(1)}` : `highest in search window, S/N ${c.peak_snr.toFixed(1)}`],
      textposition: 'top right', textfont: { color: detected ? '#f59e0b' : muted.value, size: 11 },
      marker: detected ? { symbol: 'circle-open', size: 16, color: '#f59e0b', line: { width: 3 } }
        : { symbol: 'circle-open', size: 12, color: muted.value, line: { width: 1 }, opacity: 0.8 } })
  }
  // The highest point anywhere in the map, to compare with the peak in the
  // search window: a window placed on the CHIME values always has a peak
  // there, and it means little if the map has higher points elsewhere
  const tr = mapTrace(c)
  let best = { v: -Infinity, x: 0, y: 0 }
  c.mapRows.forEach((row, i) => row.forEach((v, j) => { if (v > best.v) best = { v, x: tr.x[j], y: tr.y[i] } }))
  if (isFinite(best.v)) {
    traces.push({ type: 'scatter', mode: 'markers+text', x: [best.x], y: [best.y],
      text: [`highest in the map, S/N ${best.v.toFixed(1)}`], textposition: 'bottom right', textfont: { color: ink.value, size: 11 },
      marker: { symbol: 'diamond-open', size: 13, color: ink.value, line: { width: 2 } } })
  }
  // where CHIME measured the burst: its DM, at its arrival time
  traces.push({ type: 'scatter', mode: 'markers+text', x: [0], y: [s.dm_chime], text: ['CHIME'], textposition: 'top left',
    textfont: { color: '#38bdf8', size: 11 }, marker: { symbol: 'x-thin-open', size: 14, color: '#38bdf8', line: { color: '#38bdf8', width: 2 } } })
  Plotly.react(el, traces, {
    height: 360, margin: { l: 70, r: 10, t: 10, b: 45 }, paper_bgcolor: paper.value, plot_bgcolor: paper.value, font: font.value,
    hovermode: false, showlegend: false, coloraxis: colorAxis.value,
    xaxis: axis('Arrival at 400 MHz relative to CHIME (s)'), yaxis: axis('Trial DM (pc cm⁻³)'),
    shapes: [-s.search_tau_s, s.search_tau_s].map(x => ({ type: 'line', xref: 'x', yref: 'paper', x0: x, x1: x, y0: 0, y1: 1,
      line: { color: dark.value ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.6)', dash: 'dash', width: 1 } }))
  }, { displaylogo: false, responsive: true })
}

function drawBandMaps() {
  const el = bandMapDiv.value
  const rows = bandTransforms.value.filter(t => t.mapRows)
  if (!el || !el.clientWidth || !rows.length) return
  const n = rows.length
  const gap = 0.3 / n / 2
  const layout: Record<string, any> = {
    height: n * 150 + 70, margin: { l: 70, r: 10, t: 20, b: 45 }, paper_bgcolor: paper.value, plot_bgcolor: paper.value,
    font: font.value, hovermode: false, showlegend: false, coloraxis: colorAxis.value, annotations: []
  }
  const traces = rows.map((t, i) => {
    const s = i == 0 ? '' : String(i + 1)
    const top = 1 - i / n
    const b = bandOf(t.chan0)
    layout[`xaxis${s}`] = { ...axis(i == n - 1 ? 'Arrival at 400 MHz relative to CHIME (s)' : ''), anchor: `y${s}` }
    layout[`yaxis${s}`] = { ...axis('DM'), anchor: `x${s}`, domain: [top - 1 / n + gap, top - gap] }
    layout.annotations.push({ xref: 'paper', yref: 'paper', x: 0, y: top - gap, xanchor: 'left', yanchor: 'bottom', showarrow: false,
      text: b ? `${bandName(b)} · smearing ${fmt(b.smear_s)} s` : '', font: { color: ink.value, size: 12 } })
    return mapTrace(t, `x${s}`, `y${s}`)
  })
  Plotly.react(el, traces, layout, { displaylogo: false, responsive: true })
}

function drawAll() { drawGrid(); drawCurves(); drawMap(); drawBandMaps() }
watch([data, dark], () => nextTick(drawAll))
watch(pixel, () => nextTick(drawGrid))

const observer = import.meta.client ? new ResizeObserver(() => drawAll()) : null
watch([gridDiv, curveDiv, mapDiv, bandMapDiv], (els, old) => {
  old?.forEach(e => e && observer?.unobserve(e))
  els.forEach(e => e && observer?.observe(e))
}, { immediate: true })
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div id="dmt" class="mt-2 space-y-2">
    <UCard :ui="{ body: { padding: 'px-3 py-3 sm:p-4' } }" class="relative">
      <UProgress v-if="pending" animation="elastic" size="xs" class="p-0 m-0 top-0 left-0 absolute" />
      <h2 class="text-xl font-semibold">Dispersion measure transform</h2>
      <template v-if="data?.computed && summary && hasData">
        <p class="mt-2 text-sm text-gray-600 dark:text-gray-300 max-w-5xl">
          Every pixel of the 5x5 grid around the source is searched at trial DMs from {{ fmt(summary.dm_lo, 1) }} to
          {{ fmt(summary.dm_hi, 1) }} pc cm⁻³ in steps of {{ summary.dm_step }}, at the full 83.6 ms resolution. RFI is masked
          and the data detrended with the CHIME/FRB clipping and detrending chain, each band is transformed with the FDMT, and
          its dedispersed time series are searched with boxcars up to its smearing. The bands are then combined on a common time
          axis, referenced to the arrival CHIME measured at 400 MHz, which pins down the DM far more tightly than one band. The search window
          spans {{ summary.search_tau_s }} s around the CHIME arrival beyond the smearing, and the threshold is S/N
          {{ summary.snr_threshold }}.
        </p>
        <UAlert class="mt-3" :color="summary.detected ? 'amber' : 'blue'" variant="soft"
          :icon="summary.detected ? 'i-heroicons-sparkles' : 'i-heroicons-information-circle'" :title="verdict" />
        <UTable :rows="bandRows" :columns="bandColumns" class="mt-3" :ui="{ td: { base: 'whitespace-normal' } }" />
        <p class="mt-2 text-xs text-gray-500 dark:text-gray-400 max-w-5xl">
          The EPIC images are not flux calibrated, so the fluence limits use the radiometer equation with a model array. The
          system temperature is the sky (60 K λ^2.55) plus 250 K, and the effective area is 229 dipoles of λ²/3 each, capped at
          the station footprint and projected to the source elevation. The limits assume a burst as wide as the smearing.
        </p>
      </template>
      <p v-else-if="data?.computed && summary" class="mt-2 text-sm text-gray-600 dark:text-gray-300">
        No band recorded the source during the watch, so there is nothing to transform.
      </p>
      <p v-else-if="!pending" class="mt-2 text-sm text-gray-600 dark:text-gray-300">
        The DM transform of this event has not been computed yet. It runs on the worker nodes after the watch ends, and the bands are
        combined once all of them are done.
      </p>
    </UCard>

    <template v-if="data?.computed && summary && hasData">
      <div class="grid gap-2 lg:grid-cols-3">
        <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-2' } }">
          <div class="px-2 pt-1 text-sm font-medium">Peak S/N of every pixel, all bands combined</div>
          <div class="px-2 text-xs text-gray-500 dark:text-gray-400">Select a pixel to show its transforms</div>
          <div ref="gridDiv" class="w-full" />
        </UCard>
        <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-2' } }" class="lg:col-span-2 relative transition-opacity" :class="pending ? 'opacity-50' : ''">
          <UProgress v-if="pending" animation="carousel" size="xs" class="absolute top-0 left-0" />
          <div class="px-2 pt-1 text-sm font-medium">
            S/N against trial DM, pixel ({{ pixel.px }}, {{ pixel.py }})
          </div>
          <div class="px-2 text-xs text-gray-500 dark:text-gray-400">Dashed at the CHIME DM, dotted at the S/N threshold</div>
          <div ref="curveDiv" class="w-full" />
        </UCard>
      </div>
      <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-2' } }" class="relative transition-opacity" :class="pending ? 'opacity-50' : ''">
        <UProgress v-if="pending" animation="carousel" size="xs" class="absolute top-0 left-0" />
        <div class="px-2 pt-1 text-sm font-medium">
          DM against arrival time, all bands combined, pixel ({{ pixel.px }}, {{ pixel.py }})
        </div>
        <div class="px-2 text-xs text-gray-500 dark:text-gray-400">The transforms of the bands with data, aligned on the arrival at 400 MHz and
          stacked as the sum of their S/N over the square root of their number. Dashed lines bound the search window. The circle marks the highest point in the search window, the diamond the
          highest point anywhere in the map, and the blue cross the DM and arrival time CHIME measured</div>
        <div ref="mapDiv" class="w-full" />
      </UCard>
      <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-2' } }" class="relative transition-opacity" :class="pending ? 'opacity-50' : ''">
        <UProgress v-if="pending" animation="carousel" size="xs" class="absolute top-0 left-0" />
        <div class="px-2 pt-1 text-sm font-medium">DM against arrival time in each band, pixel ({{ pixel.px }}, {{ pixel.py }})</div>
        <div ref="bandMapDiv" class="w-full" />
      </UCard>
    </template>
  </div>
</template>
