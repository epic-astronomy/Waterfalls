<script setup lang="ts">
// Spectrogram of one sky position from the all-sky monitors, one panel per
// band. The monitors track the position on a fixed HEALPix grid, so the
// spectrogram follows the same patch of sky however long it is.
import Plotly from 'plotly.js-dist-min'
import { v4 as uuidv4 } from 'uuid'

interface PixelBand {
  node: string, up: boolean, error?: string, hpix?: number, ra?: number, dec?: number,
  tracked?: boolean, el?: number, kind?: string, interval_s?: number,
  times?: number[], freqs_mhz?: number[], shape?: number[], data_b64?: string
}

const props = defineProps<{
  ra: number, dec: number, hours: number,
  // a burst to mark: its arrival time at infinite frequency (unix s) and DM
  tInf?: number | null, dm?: number | null
}>()

const rtConfig = useRuntimeConfig()
const colorMode = useColorMode()
const tz = useTimeZone()
const bands = ref<PixelBand[]>([])
const pending = ref(false)
const error = ref('')
const normOn = useState('skymon-normalise', () => true)
const divId = `skymon-${uuidv4()}`
const K_DM = 4148.808

function decode(b: PixelBand): Float32Array[] {
  const [nt, nc] = b.shape ?? [0, 0]
  const bin = atob(b.data_b64 ?? '')
  const buf = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i)
  const flat = new Float32Array(buf.buffer)
  // rows are channels for the heatmap
  const rows: Float32Array[] = []
  for (let c = 0; c < nc; c++) {
    const r = new Float32Array(nt)
    for (let t = 0; t < nt; t++) r[t] = flat[t * nc + c]
    rows.push(r)
  }
  return rows
}

// each channel as its departure from its median in units of its robust scatter
function normalise(row: Float32Array) {
  const v = Array.from(row).filter(x => x === x).sort((a, b) => a - b)
  if (v.length < 8) return row
  const med = v[v.length >> 1]
  const dev = v.map(x => Math.abs(x - med)).sort((a, b) => a - b)
  const sig = 1.4826 * dev[dev.length >> 1]
  return sig > 0 ? row.map(x => (x - med) / sig) : row
}

function robustRange(rows: Float32Array[]) {
  const v: number[] = []
  for (const r of rows) for (let t = 0; t < r.length; t += Math.max(1, r.length >> 7)) if (r[t] === r[t]) v.push(r[t])
  if (v.length < 2) return {}
  v.sort((a, b) => a - b)
  return { zmin: v[Math.floor(0.01 * (v.length - 1))], zmax: v[Math.ceil(0.99 * (v.length - 1))] }
}

async function load() {
  pending.value = true
  error.value = ''
  try {
    bands.value = await $fetch<PixelBand[]>(rtConfig.public.fastapiBase + '/skymon/pixel', {
      query: { ra: props.ra, dec: props.dec, hours: props.hours }
    })
  } catch {
    error.value = 'The monitors could not be reached.'
    bands.value = []
  } finally {
    pending.value = false
  }
  await nextTick()
  draw()
}

const shown = computed(() => bands.value.filter(b => b.up && b.tracked && (b.times?.length ?? 0) > 1))
const notShown = computed(() => bands.value.filter(b => !(b.up && b.tracked && (b.times?.length ?? 0) > 1)))

function draw() {
  const el = document.getElementById(divId)
  if (!el) return
  const dark = colorMode.value == 'dark'
  const ink = dark ? 'white' : 'black'
  const n = shown.value.length
  if (!n) { Plotly.purge(el); return }
  const traces: any[] = []
  const layout: any = {
    height: Math.max(260, 230 * n + 60),
    margin: { t: 20, b: 55, l: 75, r: 20 },
    paper_bgcolor: dark ? '#131826' : 'rgb(255,255,255)',
    plot_bgcolor: dark ? '#374151' : '#d1d5db',
    showlegend: false, hovermode: 'closest',
    grid: { rows: n, columns: 1, pattern: 'independent', roworder: 'bottom to top' }
  }
  shown.value.forEach((b, i) => {
    let rows = decode(b)
    if (normOn.value) rows = rows.map(normalise)
    const x = (b.times ?? []).map(t => tz.plotTime(t * 1000))
    const y = b.freqs_mhz ?? []
    const ax = i ? String(i + 1) : ''
    traces.push({
      z: rows, x, y, type: 'heatmap', xaxis: 'x' + ax, yaxis: 'y' + ax, hoverongaps: false,
      showscale: false, colorscale: 'Viridis', zsmooth: false, ...robustRange(rows),
      hovertemplate: '%{x}<br>%{y:.3f} MHz<br>%{z:.2f}<extra>' + b.node + '</extra>'
    })
    if (props.tInf != null && props.dm != null && y.length) {
      // arrival of the burst across this band
      const fs = [y[0], y[y.length - 1]]
      const ts = fs.map(f => tz.plotTime((props.tInf! + K_DM * props.dm! / (f * f)) * 1000))
      traces.push({ x: ts, y: fs, xaxis: 'x' + ax, yaxis: 'y' + ax, mode: 'lines', type: 'scatter',
        line: { color: dark ? '#fbbf24' : '#b45309', width: 2, dash: 'dot' }, hoverinfo: 'skip' })
    }
    layout['xaxis' + ax] = {
      tickfont: { color: ink }, tickcolor: ink,
      title: i == 0 ? { text: `Time (${tz.zoneName()})`, font: { color: ink } } : undefined
    }
    layout['yaxis' + ax] = {
      tickfont: { color: ink }, tickcolor: ink,
      title: { text: `${b.node} (MHz)`, font: { color: ink, size: 12 } }
    }
  })
  Plotly.react(el, traces, layout, { displaylogo: false, responsive: true })
}

watch(() => [props.ra, props.dec, props.hours], load)
watch([normOn, colorMode, () => tz.mode.value, () => props.tInf, () => props.dm], () => draw())
onMounted(load)
onBeforeUnmount(() => { const el = document.getElementById(divId); if (el) Plotly.purge(el) })
</script>

<template>
  <UCard :ui="{ body: { padding: 'p-2 sm:p-3' } }">
    <div class="flex flex-wrap items-center gap-3 px-1 pb-2 text-sm">
      <span class="font-medium">RA {{ ra.toFixed(2) }}°, Dec {{ dec.toFixed(2) }}°</span>
      <span v-if="shown[0]" class="text-gray-500 dark:text-gray-400">
        HEALPix {{ shown[0].hpix }} (nside {{ shown[0].nside }}), {{ shown[0].interval_s?.toFixed(1) }} s per row
      </span>
      <div class="flex-1" />
      <UCheckbox v-model="normOn" label="Normalise channels" />
      <UButton size="xs" variant="outline" icon="i-heroicons-arrow-path" label="Reload" :loading="pending" @click="load" />
    </div>
    <UProgress v-if="pending" animation="carousel" size="xs" />
    <UAlert v-if="error" color="red" variant="soft" icon="i-heroicons-exclamation-triangle" :title="error" />
    <div :id="divId" />
    <p v-if="!pending && !shown.length && !error" class="text-center text-gray-500 dark:text-gray-400 py-6">
      No monitor tracks this position in the selected time span. A position is tracked while it is above the elevation limit.
    </p>
    <p v-if="notShown.length && !pending" class="px-1 pt-2 text-xs text-gray-500 dark:text-gray-400">
      Without data for this position
      <span v-for="(b, i) in notShown" :key="b.node">{{ i ? ', ' : ' ' }}{{ b.node }}<template v-if="!b.up"> (monitor not answering)</template><template v-else-if="!b.tracked"> (below the horizon)</template></span>.
    </p>
  </UCard>
</template>
