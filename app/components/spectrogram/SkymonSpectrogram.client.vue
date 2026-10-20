<script setup lang="ts">
// Spectrogram of one pixel of an all-sky monitor, drawn as on the LWA-SV and
// FRB pages. Live shows the monitor's latest search window at the image
// cadence (normalised by the monitor); Averages shows its accumulation, 10 s
// per row, over up to six hours. Both update while the page is open.
import Plotly from 'plotly.js-dist-min'
import { v4 as uuidv4 } from 'uuid'

interface PixelBand {
  node: string, up: boolean, error?: string, hpix?: number, nside?: number, ra?: number, dec?: number,
  tracked?: boolean, el?: number, kind?: string, interval_s?: number,
  times?: number[], freqs_mhz?: number[], shape?: number[], data_b64?: string
}

const props = defineProps<{
  node: string, ra: number, dec: number, hpix?: number | null,
  // image cadence of the monitor's band (s)
  dtImage?: number | null,
  // a burst to mark: arrival at infinite frequency (unix s) and DM
  tInf?: number | null, dm?: number | null
}>()

const rtConfig = useRuntimeConfig()
const colorMode = useColorMode()
const tz = useTimeZone()
const K_DM = 4148.808

const resolution = useState<'live' | 'avg'>('skymon-spec-resolution', () => 'live')
const hours = useState('skymon-spec-hours', () => 1)
const normOn = useState('skymon-spec-normalise', () => true)
const rfiOn = useState('skymon-spec-flag-rfi', () => false)
const autoOn = useState('skymon-spec-auto', () => true)
const showDispersion = ref(true)

const band = shallowRef<PixelBand | null>(null)
let rows: Float32Array[] = []
let times: number[] = []  // of rows (unix s)
// Live: the monitor keeps only its latest search window (about 30 s), so the windows
// are joined here as they come, for up to LIVE_SPAN_S while the pixel is shown
const LIVE_SPAN_S = 600
// the part of it shown
const liveSpan = useState('skymon-live-span', () => 60)
const liveSpans = [{ label: 'last 30 s', value: 30 }, { label: 'last 1 min', value: 60 }, { label: 'last 2 min', value: 120 },
  { label: 'last 5 min', value: 300 }, { label: 'last 10 min', value: 600 }]
let liveT: number[] = []
let liveRows: Float32Array[] = []
function resetLive() { liveT = []; liveRows = [] }
function joinLive(t: number[], r: Float32Array[]) {
  const dt = props.dtImage ?? 0.0836
  const last = liveT.length ? liveT[liveT.length - 1] : -Infinity
  const k = t.findIndex(x => x > last + dt / 2)
  if (k < 0) return
  const gap = liveT.length && t[k] - last > 3 * dt
  const nc = r.length
  if (!liveRows.length) liveRows = Array.from({ length: nc }, () => new Float32Array(0))
  const add = (gap ? 1 : 0) + t.length - k
  // a blank column where windows were missed (the tab hidden, a slow reply)
  const newT = [...liveT, ...(gap ? [last + dt] : []), ...t.slice(k)]
  const drop = Math.max(0, newT.findIndex(x => x >= newT[newT.length - 1] - LIVE_SPAN_S))
  liveRows = liveRows.map((row, c) => {
    const out = new Float32Array(row.length + add)
    out.set(row)
    if (gap) out[row.length] = NaN
    out.set(r[c].subarray(k), row.length + (gap ? 1 : 0))
    return drop ? out.subarray(drop) : out
  })
  liveT = newT.slice(drop)
}
const pending = ref(false)
const error = ref('')
const divId = `skymon-spec-${uuidv4()}`
const plotDiv = ref<HTMLElement>()

function decode(b: PixelBand) {
  const [nt, nc] = b.shape ?? [0, 0]
  const flat = new Float32Array(Uint8Array.from(atob(b.data_b64 ?? ''), c => c.charCodeAt(0)).buffer)
  const out: Float32Array[] = []
  for (let c = 0; c < nc; c++) {
    const r = new Float32Array(nt)
    for (let t = 0; t < nt; t++) r[t] = flat[t * nc + c]
    out.push(r)
  }
  return out
}

// each channel as its departure from its median in units of its robust scatter
function normaliseChannel(row: Float32Array) {
  const v = Array.from(row).filter(x => x === x).sort((a, b) => a - b)
  if (v.length < 8) return
  const med = v[v.length >> 1]
  const dev = v.map(x => Math.abs(x - med)).sort((a, b) => a - b)
  const sig = 1.4826 * dev[dev.length >> 1]
  if (sig > 0) for (let t = 0; t < row.length; t++) row[t] = (row[t] - med) / sig
}

function robustRange(z: Float32Array[]) {
  const v: number[] = []
  const n = z.reduce((a, r) => a + r.length, 0)
  const step = Math.max(1, Math.floor(n / 20000))
  let k = 0
  for (const r of z) for (let t = 0; t < r.length; t++, k++) if (k % step == 0 && isFinite(r[t])) v.push(r[t])
  if (v.length < 2) return {}
  v.sort((a, b) => a - b)
  return { zmin: v[Math.floor(0.01 * (v.length - 1))], zmax: v[Math.ceil(0.99 * (v.length - 1))] }
}

// RFI flagging as on the LWA-SV page (lib/rfi.ts), off the main thread
let rfiWorker: Worker | null = null
let rfiRequest = 0
const rfiMask = shallowRef<Uint8Array[] | null>(null)
const rfiPending = ref(false)
const rfiFlagged = computed(() => {
  const m = rfiMask.value
  if (!m) return null
  let bad = 0, n = 0
  for (const r of m) { n += r.length; for (let t = 0; t < r.length; t++) bad += 1 - r[t] }
  return n ? 100 * bad / n : 0
})
function requestRfi() {
  if (!rfiOn.value || !rows.length || rfiMask.value) return
  if (!rfiWorker) {
    rfiWorker = new Worker(new URL('../../lib/rfi.worker.ts', import.meta.url), { type: 'module' })
    rfiWorker.onmessage = (e: MessageEvent<{ id: number, mask: Uint8Array[] }>) => {
      if (e.data.id != rfiRequest) return
      rfiMask.value = e.data.mask
      rfiPending.value = false
      draw()
    }
  }
  rfiRequest++
  rfiPending.value = true
  const dt = resolution.value == 'live' ? (props.dtImage ?? 0.0836) : (band.value?.interval_s ?? 10)
  rfiWorker.postMessage({ id: rfiRequest, channels: rows.map(r => r.slice()), dt })
}

let inflight = 0
async function load() {
  const id = ++inflight
  pending.value = true
  try {
    const query: Record<string, any> = { ra: props.ra, dec: props.dec, node: props.node, hours: hours.value }
    if (props.hpix != null) query.hpix = props.hpix
    if (resolution.value == 'live') query.fine = true
    const r = await $fetch<PixelBand[]>(rtConfig.public.fastapiBase + '/skymon/pixel', { query })
    if (id != inflight) return
    const b = r.find(x => x.node == props.node) ?? null
    band.value = b
    error.value = !b?.up ? 'The monitor did not answer.' : ''
    rows = b?.up && b.tracked && (b.times?.length ?? 0) > 1 ? decode(b) : []
    times = b?.times ?? []
    if (resolution.value == 'live' && rows.length) {
      joinLive(times, rows)
      rows = liveRows
      times = liveT
    }
    rfiMask.value = null
    rfiRequest++
    rfiPending.value = false
    draw()
    requestRfi()
  } catch {
    if (id != inflight) return
    error.value = 'The monitor could not be reached.'
  } finally {
    if (id == inflight) pending.value = false
  }
}

const hasData = computed(() => !!band.value?.up && !!band.value?.tracked && (band.value?.times?.length ?? 0) > 1)

function draw() {
  const el = plotDiv.value
  if (!el) return
  if (!rows.length || !band.value) { Plotly.purge(el); return }
  // with Flag RFI on, wait for this window's mask so unflagged data never flash up
  if (rfiOn.value && !rfiMask.value) return
  if (el.clientWidth == 0) return
  const b = band.value
  const dark = colorMode.value == 'dark'
  const ink = dark ? 'white' : 'black'
  const z = rows.map(r => r.slice())
  const m = rfiOn.value ? rfiMask.value : null
  if (m) z.forEach((row, c) => { const mk = m[c]; if (mk) for (let t = 0; t < row.length; t++) if (!mk[t]) row[t] = NaN })
  if (normOn.value) z.forEach(normaliseChannel)
  // the rows shown: the joined live windows (the last liveSpan of them), or the averages
  let zs = z, ts = times
  if (resolution.value == 'live' && ts.length) {
    const t0 = ts[ts.length - 1] - liveSpan.value
    const k = Math.max(0, ts.findIndex(t => t >= t0))
    zs = zs.map(r => r.subarray(k)); ts = ts.slice(k)
  }
  // cells kept about as wide as they are tall: neighbouring samples averaged when
  // the span holds more of them than the plot has room for at that width
  const plotW = Math.max(200, el.clientWidth - 90), plotH = 450 - 100
  const cols = Math.max(1, Math.floor(plotW / Math.max(1, plotH / Math.max(1, zs.length))))
  const bin = Math.ceil(ts.length / cols)
  if (bin > 1) {
    const n = Math.floor(ts.length / bin)
    zs = zs.map(r => {
      const o = new Float32Array(n)
      for (let i = 0; i < n; i++) {
        let s = 0, m = 0
        for (let j = i * bin; j < (i + 1) * bin; j++) { const v = r[j]; if (v === v) { s += v; m++ } }
        // the mean of the samples, scaled so noise keeps its spread on the colour scale
        o[i] = m ? s / Math.sqrt(m) : NaN
      }
      return o
    })
    ts = Array.from({ length: n }, (_, i) => ts[i * bin])
  }
  const z2 = zs
  const x = ts.map(t => tz.plotTime(t * 1000))
  const y = b.freqs_mhz ?? []
  const df = y.length > 1 ? y[1] - y[0] : 0
  const fc = y.length ? (y[0] + y[y.length - 1]) / 2 : 0
  const traces: any[] = [{
    z: z2, x, y, type: 'heatmap', hoverongaps: false, ...robustRange(z2), showscale: false,
    colorscale: 'Viridis', zsmooth: 'fast'
  }]
  if (showDispersion.value && props.tInf != null && props.dm != null && y.length && times.length > 1) {
    // arrival of the burst over the window, sampled in time
    const t0 = times[0], t1 = times[times.length - 1]
    const xs: string[] = [], ys: number[] = []
    for (let i = 0; i <= 300; i++) {
      const t = t0 + (t1 - t0) * i / 300
      if (t <= props.tInf) continue
      const f = Math.sqrt(K_DM * props.dm / (t - props.tInf))
      if (f >= y[0] - df / 2 && f <= y[y.length - 1] + df / 2) { xs.push(tz.plotTime(t * 1000)); ys.push(f) }
    }
    if (xs.length) traces.push({ x: xs, y: ys, type: 'scatter', mode: 'lines',
      line: { dash: 'dash', width: 1.5, color: dark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' } })
  }
  const font = (size: number) => ({ family: 'Courier New, monospace', size, color: ink })
  const layout: any = {
    height: 450,
    margin: { t: 45, b: 55, l: 70, r: 20 },
    title: { text: `RA ${(b.ra ?? props.ra).toFixed(2)}° Dec ${(b.dec ?? props.dec).toFixed(2)}° - ${fc.toFixed(2)} MHz | LWA-Sevilleta`, font: font(20) },
    xaxis: {
      title: { text: `Time (${tz.zoneName(times.length ? times[0] * 1000 : Date.now())})`, font: font(18) },
      tickfont: { color: ink, family: 'Courier New, monospace' }, tickcolor: ink, nticks: 6,
      tickformat: resolution.value == 'live' ? '%H:%M:%S' : '%H:%M',
      range: x.length ? [x[0], x[x.length - 1]] : undefined
    },
    yaxis: {
      title: { text: 'Frequency (MHz)', font: font(18) },
      tickfont: { color: ink }, tickcolor: ink,
      range: y.length ? [y[0] - df / 2, y[y.length - 1] + df / 2] : undefined
    },
    paper_bgcolor: dark ? '#131826' : 'rgb(255,255,255)',
    plot_bgcolor: dark ? '#374151' : '#d1d5db',
    hovermode: false, showlegend: false
  }
  Plotly.react(el, traces, layout, {
    displaylogo: false, responsive: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'zoom2d', 'pan2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d'],
    toImageButtonOptions: { format: 'png', filename: `EPIC all-sky monitor ${props.node} HEALPix ${b.hpix}`, scale: 3 }
  })
}

// live windows every 5 s, averages every 30 s, while Update is on
let timer: ReturnType<typeof setInterval> | undefined
function schedule() {
  clearInterval(timer)
  if (autoOn.value) timer = setInterval(() => { if (!pending.value && !document.hidden) load() }, resolution.value == 'live' ? 5000 : 30000)
}
watch(() => [props.node, props.ra, props.dec, props.hpix], () => { band.value = null; rows = []; resetLive(); draw(); load() })
watch([resolution, hours], () => { band.value = null; rows = []; resetLive(); draw(); load(); schedule() })
watch(autoOn, schedule)
watch([normOn, liveSpan, colorMode, () => tz.mode.value, showDispersion, () => props.tInf, () => props.dm], () => draw())
watch(rfiOn, on => { if (on && !rfiMask.value) requestRfi(); else draw() })
let ro: ResizeObserver | undefined
onMounted(() => {
  load(); schedule()
  ro = new ResizeObserver(() => draw())
  if (plotDiv.value) ro.observe(plotDiv.value)
})
onBeforeUnmount(() => {
  clearInterval(timer); ro?.disconnect(); rfiWorker?.terminate()
  if (plotDiv.value) Plotly.purge(plotDiv.value)
})

</script>

<template>
  <!-- one section of the viewer: controls, then the plot, divided by a rule -->
  <div class="divide-y divide-gray-200 dark:divide-gray-800">
    <div class="pb-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
      <UCheckbox v-if="tInf != null && dm != null" v-model="showDispersion" label="Dispersion curve" />
      <UCheckbox v-model="normOn" label="Normalise" />
      <div class="flex items-center gap-2">
        <UCheckbox v-model="rfiOn" label="Flag RFI" />
        <UIcon v-show="rfiOn && rfiPending" name="i-heroicons-arrow-path-20-solid" class="w-4 h-4 animate-spin text-gray-500" />
        <span v-show="rfiOn && !rfiPending && rfiFlagged !== null" class="text-xs text-gray-500 dark:text-gray-400 tabular-nums">{{ rfiFlagged?.toFixed(1) }}%</span>
      </div>
      <USelect v-if="resolution == 'live'" v-model="liveSpan" size="xs" :items="liveSpans" />
      <UCheckbox v-model="autoOn" label="Update" />
      <span v-if="hasData" class="ml-auto text-xs text-gray-500 dark:text-gray-400 tabular-nums">
        RA {{ (band?.ra ?? ra).toFixed(2) }}°, Dec {{ (band?.dec ?? dec).toFixed(2) }}°, el {{ band?.el?.toFixed(0) }}°
      </span>
    </div>
    <div class="relative pt-2">
      <SpectrogramSkymonLoading v-if="pending && !hasData" :key="`${node}-${hpix ?? ra}-${dec}-${resolution}`" :messages="resolution == 'live' ? [
        'Asking the monitor for this pixel',
        'Reading the latest search window',
        'Receiving the spectrogram',
        'Drawing the spectrogram'] : [
        'Asking the monitor for this pixel',
        `Reading the 10 s averages of the last ${hours < 1 ? hours * 60 + ' min' : hours + ' h'}`,
        'Receiving the spectrogram',
        'Drawing the spectrogram']" />
      <UProgress v-else-if="pending" animation="carousel" size="xs" class="p-0 m-0 top-0 left-0 absolute" />
      <UAlert v-if="error" color="error" variant="soft" icon="i-heroicons-exclamation-triangle" :title="error" class="mb-1" />
      <p v-if="!pending && band && band.up && !hasData" class="p-4 text-sm text-gray-500 dark:text-gray-400">
        {{ band.tracked ? 'No data for this pixel yet.' : 'Below the elevation limit in this band.' }}
      </p>
      <div class="transition-opacity" :class="rfiOn && rfiPending ? 'opacity-40' : ''">
        <div :id="divId" ref="plotDiv" />
      </div>
    </div>
  </div>
</template>
