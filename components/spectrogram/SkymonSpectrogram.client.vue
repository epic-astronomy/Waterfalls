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
  const times = b.times ?? []
  const x = times.map(t => tz.plotTime(t * 1000))
  const y = b.freqs_mhz ?? []
  const df = y.length > 1 ? y[1] - y[0] : 0
  const fc = y.length ? (y[0] + y[y.length - 1]) / 2 : 0
  const traces: any[] = [{
    z, x, y, type: 'heatmap', hoverongaps: false, ...robustRange(z), showscale: false,
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
      tickfont: { color: ink, family: 'Courier New, monospace' }, tickcolor: ink,
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
watch(() => [props.node, props.ra, props.dec, props.hpix], () => { band.value = null; rows = []; draw(); load() })
watch([resolution, hours], () => { band.value = null; rows = []; draw(); load(); schedule() })
watch(autoOn, schedule)
watch([normOn, colorMode, () => tz.mode.value, showDispersion, () => props.tInf, () => props.dm], () => draw())
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

const resolutionOptions = computed(() => [
  { label: `Live, ${((props.dtImage ?? 0.0836) * 1000).toFixed(1)} ms`, value: 'live' },
  { label: 'Averages, 10 s', value: 'avg' }
])
const hoursOptions = [{ label: 'last 30 min', value: 0.5 }, { label: 'last 1 h', value: 1 }, { label: 'last 2 h', value: 2 }, { label: 'last 6 h', value: 6 }]
</script>

<template>
  <div>
    <UCard :ui="{ body: { padding: 'px-2 py-2 sm:p-2 m-2' } }">
      <div class="flex flex-wrap justify-center items-center gap-x-8 gap-y-2">
        <div class="flex items-center gap-2">
          <span class="text-sm">Resolution</span>
          <USelect v-model="resolution" :options="resolutionOptions" />
          <USelect v-if="resolution == 'avg'" v-model="hours" :options="hoursOptions" />
        </div>
        <div class="flex items-center gap-x-6">
          <UCheckbox v-if="tInf != null && dm != null" v-model="showDispersion" label="Dispersion curve" />
          <UCheckbox v-model="normOn" label="Normalise channels" />
          <div class="flex items-center gap-2">
            <UCheckbox v-model="rfiOn" label="Flag RFI" />
            <UIcon v-show="rfiOn && rfiPending" name="i-heroicons-arrow-path-20-solid" class="w-4 h-4 animate-spin text-gray-500" />
            <span v-show="rfiOn && !rfiPending && rfiFlagged !== null" class="text-xs text-gray-500 dark:text-gray-400 tabular-nums">{{ rfiFlagged?.toFixed(1) }}% flagged</span>
          </div>
          <UCheckbox v-model="autoOn" label="Update" />
        </div>
      </div>
    </UCard>
    <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-1 m-1' } }" class="relative">
      <SpectrogramSkymonLoading v-if="pending && !hasData" :key="`${node}-${hpix ?? ra}-${dec}-${resolution}`" :messages="resolution == 'live' ? [
        `Asking ${node} for this pixel`,
        'Reading the latest search window',
        'Receiving the spectrogram',
        'Drawing the spectrogram'] : [
        `Asking ${node} for this pixel`,
        `Reading the 10 s averages of the last ${hours < 1 ? hours * 60 + ' min' : hours + ' h'}`,
        'Receiving the spectrogram',
        'Drawing the spectrogram']" />
      <UProgress v-else-if="pending" animation="carousel" size="xs" class="p-0 m-0 top-0 left-0 absolute" />
      <UAlert v-if="error" color="red" variant="soft" icon="i-heroicons-exclamation-triangle" :title="error" class="mb-1" />
      <p v-if="!pending && band && band.up && !hasData" class="p-4 text-sm text-gray-500 dark:text-gray-400">
        {{ band.tracked ? 'No data for this pixel in the selected span yet.' : 'This monitor does not track this position. A position is tracked while it is above the elevation limit.' }}
      </p>
      <div class="transition-opacity" :class="rfiOn && rfiPending ? 'opacity-40' : ''">
        <div :id="divId" ref="plotDiv" />
      </div>
      <p v-if="hasData" class="px-2 pb-1 text-xs text-gray-500 dark:text-gray-400">
        HEALPix {{ band?.hpix }} (nside {{ band?.nside }}), elevation {{ band?.el?.toFixed(1) }}°.
        {{ band?.kind == 'fine' ? 'The latest search window, each channel normalised by the monitor.' : `Raw values, ${band?.interval_s?.toFixed(1)} s per row.` }}
      </p>
    </UCard>
  </div>
</template>
