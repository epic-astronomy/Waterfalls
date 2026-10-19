<script setup lang="ts">
// A candidate of an all-sky monitor, from the data the monitor kept with it:
// its pixel's dynamic spectrum over the burst's sweep at the search
// resolution, the DM-time plane, and the 10 s averages of the 30 min before.
// A slider over the whole span, with the data and the expected track of the
// burst behind it, picks the window the spectrogram shows.
import Plotly from 'plotly.js-dist-min'
import { v4 as uuidv4 } from 'uuid'

interface CandData {
  freqs_mhz: number[], dt_s?: number,
  dynspec?: string, dynspec_shape?: number[], dynspec_t?: number[],
  dmt?: string, dmt_shape?: number[], dmt_dm?: number[],
  accum?: string, accum_shape?: number[], accum_t?: number[],
  candidate: {
    id: string, node: string, cls: string, snr: number, dm: number, dm_step?: number, width_s: number,
    t_inf: number, t_top?: number, t_bottom?: number, ra: number, dec: number, el: number, tier: number,
    f_lo_mhz: number, f_hi_mhz: number, injection_id?: string | null,
    known_source?: { kind: string, name: string, alias?: string | null, giant_pulse?: boolean } | null, rfi_reasons?: string[],
    flux?: { fluence_jy_ms: number, fluence_err_jy_ms?: number | null } | null,
    dm_arms?: { id: string, dm: number, snr: number, tier: number }[]
  },
  // for a test injection, what was injected
  injection?: { id: string, dm: number, t_inf: number, snr_target: number } | null
}

const props = defineProps<{ node: string, id: string }>()
const emit = defineEmits<{ live: [] }>()

const rtConfig = useRuntimeConfig()
const colorMode = useColorMode()
const tz = useTimeZone()
const K_DM = 4148.808

const data = shallowRef<CandData | null>(null)
const pending = ref(false)
const error = ref('')
const normOn = useState('skymon-cand-normalise', () => true)
const showTrack = ref(true)
// the spectrum with each channel moved to the arrival at the top of the band, as
// the candidate plots of FETCH and Heimdall show it: a burst at the DM found stands upright
const dedispOn = useState('skymon-cand-dedisperse', () => false)

function dedispersed(): Float32Array[] {
  const d = data.value, c = cand.value
  if (!d?.dynspec_t?.length || !c) return dyn
  const dt = d.dynspec_t[1] - d.dynspec_t[0], n = d.dynspec_t.length
  const fTop = d.freqs_mhz[d.freqs_mhz.length - 1]
  return dyn.map((row, ch) => {
    const f = d.freqs_mhz[ch]
    const k = Math.round(K_DM * c.dm * (1 / (f * f) - 1 / (fTop * fTop)) / dt)
    const out = new Float32Array(n).fill(NaN)
    out.set(row.subarray(Math.min(n, k)), 0)
    return out
  })
}
const window_ = ref<[number, number] | null>(null)  // UTC ms; null is the whole span

// decoded arrays, rows as named: dyn[channel][time], acc[channel][time]
let dyn: Float32Array[] = [], acc: Float32Array[] = []
let zlo = -3, zhi = 4

function unpack(b64: string | undefined, shape: number[] | undefined) {
  if (!b64 || !shape) return null
  const flat = new Float32Array(Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer)
  const [r, c] = shape
  return Array.from({ length: r }, (_, i) => flat.subarray(i * c, (i + 1) * c))
}
function transpose(rows: Float32Array[]) {
  const nr = rows.length, nc = rows[0]?.length ?? 0
  return Array.from({ length: nc }, (_, c) => { const o = new Float32Array(nr); for (let r = 0; r < nr; r++) o[r] = rows[r][c]; return o })
}
// each channel as its departure from its median in units of its robust scatter
function normaliseRow(row: Float32Array) {
  const v = Array.from(row).filter(x => x === x).sort((a, b) => a - b)
  if (v.length < 8) return row
  const med = v[v.length >> 1]
  const dev = v.map(x => Math.abs(x - med)).sort((a, b) => a - b)
  const sig = 1.4826 * dev[dev.length >> 1]
  return sig > 0 ? row.map(x => (x - med) / sig) : row
}
function percentiles(rows: Float32Array[], p0: number, p1: number) {
  const v: number[] = []
  for (const r of rows) for (let t = 0; t < r.length; t++) if (r[t] === r[t]) v.push(r[t])
  if (v.length < 2) return [-3, 4]
  v.sort((a, b) => a - b)
  return [v[Math.floor(p0 * (v.length - 1))], v[Math.ceil(p1 * (v.length - 1))]]
}

function prepare() {
  const d = data.value
  if (!d) return
  dyn = unpack(d.dynspec, d.dynspec_shape) ?? []
  acc = transpose(unpack(d.accum, d.accum_shape) ?? [])
  if (normOn.value) { dyn = dyn.map(normaliseRow); acc = acc.map(normaliseRow) }
  ;[zlo, zhi] = percentiles(dyn.length ? dyn : acc, 0.01, 0.99)
}

async function load() {
  pending.value = true
  error.value = ''
  try {
    data.value = await $fetch<CandData>(rtConfig.public.fastapiBase + `/skymon/${props.node}/candidates/${encodeURIComponent(props.id)}/data`)
    prepare()
    // open on the sweep, with as much again either side
    const s = sweep.value
    if (s) {
      const pad = Math.max(5, s[1] - s[0])
      window_.value = [(s[0] - pad) * 1000, (s[1] + pad) * 1000]
    } else window_.value = null
  } catch (e: any) {
    data.value = null
    error.value = e?.statusCode == 404 ? 'The monitor kept no data for this candidate.' : 'The monitor could not be reached.'
  } finally {
    pending.value = false
  }
  await nextTick()
  drawAll()
}

const cand = computed(() => data.value?.candidate ?? null)
const band = computed(() => {
  const f = data.value?.freqs_mhz ?? []
  const df = f.length > 1 ? f[1] - f[0] : 0
  return f.length ? { lo: f[0] - df / 2, hi: f[f.length - 1] + df / 2, df } : null
})
// arrival of the burst at a frequency (unix s)
const arrival = (f: number) => cand.value!.t_inf + K_DM * cand.value!.dm / (f * f)
// the sweep through the band: arrival at its top and at its bottom
const sweep = computed<[number, number] | null>(() => cand.value && band.value ? [arrival(band.value.hi), arrival(band.value.lo)] : null)
// the span on the slider: the chosen minutes of context before the sweep, up to the end of the data
const contextMin = useState('skymon-cand-context', () => 2)
const span = computed(() => {
  const d = data.value
  if (!d) return null
  const ts = [...(d.accum_t ?? []), ...(d.dynspec_t ?? [])]
  if (!ts.length) return null
  const last = d.accum_t?.length ? d.accum_t[d.accum_t.length - 1] + (d.accum_t[1] - d.accum_t[0] || 10) : -Infinity
  const first = Math.min(...ts)
  const from = sweep.value ? Math.max(first, sweep.value[0] - 60 * contextMin.value) : first
  return [from * 1000, Math.max(Math.max(...ts), last) * 1000] as [number, number]
})
// a window outside the new span would leave the slider in an odd state
watch(span, sp => {
  const w = window_.value
  if (sp && w && (w[0] < sp[0] || w[1] > sp[1])) window_.value = w[1] <= sp[0] || w[0] >= sp[1] ? null : [Math.max(w[0], sp[0]), Math.min(w[1], sp[1])]
  nextTick(drawAll)
})

// --- the slider's background: the data at a glance and the expected track
const VIRIDIS = ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
const lut = (() => {
  const rgb = VIRIDIS.map(h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)))
  const out = new Uint8ClampedArray(256 * 3)
  for (let i = 0; i < 256; i++) {
    const x = i / 255 * (rgb.length - 1), k = Math.min(rgb.length - 2, Math.floor(x)), f = x - k
    for (let c = 0; c < 3; c++) out[i * 3 + c] = rgb[k][c] + (rgb[k + 1][c] - rgb[k][c]) * f
  }
  return out
})()
const bg = ref<HTMLCanvasElement>()
function drawBackground() {
  const cv = bg.value, d = data.value, sp = span.value, b = band.value
  if (!cv || !d || !sp || !b) return
  const W = cv.clientWidth, H = cv.clientHeight
  if (!W || !H) return
  cv.width = W; cv.height = H
  const ctx = cv.getContext('2d')!
  const img = ctx.createImageData(W, H)
  const px = img.data
  const at = d.accum_t ?? [], dt = d.dynspec_t ?? []
  const accDt = at.length > 1 ? at[1] - at[0] : 10
  const nch = d.freqs_mhz.length
  // the colour range of the averages on their own, so they are not washed out
  const [alo, ahi] = percentiles(acc, 0.02, 0.98)
  for (let x = 0; x < W; x++) {
    const t = (sp[0] + (sp[1] - sp[0]) * (x + 0.5) / W) / 1000
    let col: ((c: number) => number) | null = null, lo = alo, hi = ahi
    if (dt.length && t >= dt[0] && t <= dt[dt.length - 1]) {
      const i = Math.min(dt.length - 1, Math.round((t - dt[0]) / (dt[1] - dt[0])))
      col = c => dyn[c]?.[i]; lo = zlo; hi = zhi
    } else if (at.length && t >= at[0] && t < at[at.length - 1] + accDt) {
      const i = Math.min(at.length - 1, Math.floor((t - at[0]) / accDt))
      col = c => acc[c]?.[i]
    }
    for (let y = 0; y < H; y++) {
      const o = (y * W + x) * 4
      const c = Math.min(nch - 1, Math.floor((1 - (y + 0.5) / H) * nch))  // top is the highest frequency
      const v = col ? col(c) : NaN
      if (v === v) {
        const k = Math.round(Math.max(0, Math.min(1, (v - lo) / (hi - lo))) * 255) * 3
        px[o] = lut[k]; px[o + 1] = lut[k + 1]; px[o + 2] = lut[k + 2]; px[o + 3] = 200
      } else px[o + 3] = 0
    }
  }
  ctx.putImageData(img, 0, 0)
  const sw = sweep.value
  if (sw) {
    const X = (t: number) => (t * 1000 - sp[0]) / (sp[1] - sp[0]) * W
    // the sweep, at least a few pixels wide however long the span
    const x0 = X(sw[0]), x1 = Math.max(X(sw[1]), x0 + 4)
    ctx.fillStyle = 'rgba(251, 191, 36, 0.28)'
    ctx.fillRect(x0 - 2, 0, x1 - x0 + 4, H)
    ctx.strokeStyle = 'rgba(251, 191, 36, 0.95)'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    for (let i = 0; i <= 40; i++) {
      const f = b.hi - (b.hi - b.lo) * i / 40
      const x = x0 + (X(arrival(f)) - X(sw[0])) * (x1 - x0) / Math.max(1e-9, X(sw[1]) - X(sw[0]))
      const y = (b.hi - f) / (b.hi - b.lo) * H
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)
    }
    ctx.stroke()
  }
}

// --- the spectrogram of the window, with the dedispersed pulse above it, and the DM-time plane
const mainDiv = ref<HTMLElement>()
const dmtDiv = ref<HTMLElement>()
const mainId = `skymon-cand-${uuidv4()}`, dmtId = `skymon-dmt-${uuidv4()}`

function profile() {
  const d = data.value, c = cand.value, b = band.value
  if (!d?.dynspec_t?.length || !c || !b || !dyn.length) return null
  const t = d.dynspec_t, dt = t[1] - t[0], n = t.length
  const fTop = d.freqs_mhz[d.freqs_mhz.length - 1]
  const shift = d.freqs_mhz.map(f => Math.round(K_DM * c.dm * (1 / (f * f) - 1 / (fTop * fTop)) / dt))
  const y: (number | null)[] = []
  for (let i = 0; i < n; i++) {
    let s = 0, m = 0
    for (let ch = 0; ch < dyn.length; ch++) {
      const j = i + shift[ch]
      if (j < n) { const v = dyn[ch][j]; if (v === v) { s += v; m++ } }
    }
    // the mean over channels, in units of its noise if the channels are independent
    y.push(m > dyn.length / 4 ? s / Math.sqrt(m) : null)
  }
  return { x: t.map(v => tz.plotTime(v * 1000)), y }
}

function drawMain() {
  const el = mainDiv.value, d = data.value, c = cand.value, b = band.value
  if (!el || !d || !c || !b || !el.clientWidth) return
  const dark = colorMode.value == 'dark'
  const ink = dark ? 'white' : 'black'
  const font = (size: number) => ({ family: 'Courier New, monospace', size, color: ink })
  const traces: any[] = []
  const heat = { type: 'heatmap', hoverongaps: false, showscale: false, colorscale: 'Viridis', zsmooth: false, zmin: zlo, zmax: zhi, xaxis: 'x', yaxis: 'y' }
  if (d.accum_t?.length && acc.length) {
    const [alo, ahi] = percentiles(acc, 0.02, 0.98)
    const dtA = d.accum_t.length > 1 ? d.accum_t[1] - d.accum_t[0] : 10
    // rows start at their time; centre them on their 10 s
    traces.push({ ...heat, z: acc, zmin: alo, zmax: ahi, x: d.accum_t.map(t => tz.plotTime((t + dtA / 2) * 1000)), y: d.freqs_mhz })
  }
  if (d.dynspec_t?.length && dyn.length)
    traces.push({ ...heat, z: dedispOn.value ? dedispersed() : dyn, x: d.dynspec_t.map(t => tz.plotTime(t * 1000)), y: d.freqs_mhz })
  if (showTrack.value && dedispOn.value && sweep.value) {
    // dedispersed, the burst's track is the arrival at the top of the band, in every channel
    const x = tz.plotTime(sweep.value[0] * 1000)
    traces.push({ x: [x, x], y: [b.lo, b.hi], type: 'scatter', mode: 'lines', xaxis: 'x', yaxis: 'y', hoverinfo: 'skip',
      line: { dash: 'dash', width: 1.5, color: dark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' } })
  } else if (showTrack.value) {
    const xs: string[] = [], ys: number[] = []
    for (let i = 0; i <= 200; i++) {
      const f = b.hi - (b.hi - b.lo) * i / 200
      xs.push(tz.plotTime(arrival(f) * 1000)); ys.push(f)
    }
    traces.push({ x: xs, y: ys, type: 'scatter', mode: 'lines', xaxis: 'x', yaxis: 'y', hoverinfo: 'skip',
      line: { dash: 'dash', width: 1.5, color: dark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' } })
  }
  const inj = d.injection
  if (showTrack.value && inj && !dedispOn.value) {
    const xs: string[] = [], ys: number[] = []
    for (let i = 0; i <= 200; i++) {
      const f = b.hi - (b.hi - b.lo) * i / 200
      xs.push(tz.plotTime((inj.t_inf + K_DM * inj.dm / (f * f)) * 1000)); ys.push(f)
    }
    traces.push({ x: xs, y: ys, type: 'scatter', mode: 'lines', xaxis: 'x', yaxis: 'y', hoverinfo: 'skip',
      line: { dash: 'dot', width: 2, color: dark ? '#fbbf24' : '#b45309' } })
  }
  const p = profile()
  if (p) traces.push({ ...p, type: 'scatter', mode: 'lines', xaxis: 'x', yaxis: 'y2', hoverinfo: 'skip',
    line: { width: 1.2, color: dark ? '#fbbf24' : '#b45309' } })
  const w = window_.value ?? span.value!
  const fc = (b.lo + b.hi) / 2
  Plotly.react(el, traces, {
    height: 520,
    margin: { t: 45, b: 55, l: 70, r: 20 },
    title: { text: `${clsTitle.value} S/N ${c.snr.toFixed(1)}, DM ${c.dm.toFixed(1)} - ${fc.toFixed(2)} MHz | LWA-Sevilleta`,
      font: font(el.clientWidth < 760 ? 14 : 18) },
    xaxis: { range: [tz.plotTime(w[0]), tz.plotTime(w[1])], title: { text: `Time (${tz.zoneName(w[0])})`, font: font(16) },
      tickfont: { color: ink, family: 'Courier New, monospace' }, tickcolor: ink, anchor: 'y', tickformat: '%H:%M:%S', nticks: 6 },
    yaxis: { domain: [0, 0.74], range: [b.lo, b.hi], title: { text: 'Frequency (MHz)', font: font(16) }, tickfont: { color: ink }, tickcolor: ink },
    yaxis2: { domain: [0.79, 1], title: { text: 'S/N', font: font(13) }, tickfont: { color: ink }, tickcolor: ink, zeroline: false },
    paper_bgcolor: dark ? '#131826' : 'rgb(255,255,255)',
    plot_bgcolor: dark ? '#374151' : '#d1d5db',
    hovermode: false, showlegend: false
  }, {
    displaylogo: false, responsive: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'zoom2d', 'pan2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d'],
    toImageButtonOptions: { format: 'png', filename: `EPIC all-sky monitor ${c.node} ${c.id}`, scale: 3 }
  })
}

// The DM-time plane from the dynamic spectrum, at trial DMs centred on the
// candidate's (half of it either side, at least 20 steps of one sample of
// delay), so the burst is in the middle whatever the range of the search tier
// that found it. Each row is the spectrum summed along the track of its DM,
// at the arrival at the top of the band, in units of its noise.
function dmtPlane() {
  const d = data.value, c = cand.value, b = band.value
  if (!d?.dynspec_t?.length || !c || !b || !dyn.length) return null
  const t = d.dynspec_t, dt = t[1] - t[0], n = t.length
  const f = d.freqs_mhz, fTop = f[f.length - 1]
  const step = dt / (K_DM * (b.lo ** -2 - b.hi ** -2))
  const half = Math.max(0.5 * c.dm, 20 * step)
  const lo = Math.max(0, c.dm - half), hi = c.dm + half
  const ntr = 121
  const dms = Array.from({ length: ntr }, (_, i) => lo + (hi - lo) * i / (ntr - 1))
  const minCh = dyn.length / 2
  const z = dms.map(dm => {
    const shift = f.map(fc => Math.round(K_DM * dm * (1 / (fc * fc) - 1 / (fTop * fTop)) / dt))
    const row = new Float32Array(n)
    for (let i = 0; i < n; i++) {
      let s = 0, m = 0
      for (let ch = 0; ch < dyn.length; ch++) {
        const j = i + shift[ch]
        if (j < n) { const v = dyn[ch][j]; if (v === v) { s += v; m++ } }
      }
      row[i] = m >= minCh ? s / Math.sqrt(m) : NaN
    }
    return row
  })
  return { z, dms, x: t.map(v => tz.plotTime(v * 1000)) }
}

function drawDmt() {
  const el = dmtDiv.value, d = data.value, c = cand.value
  if (!el || !d?.dynspec_t || !c || !el.clientWidth) return
  const plane = dmtPlane()
  if (!plane) return
  const dark = colorMode.value == 'dark'
  const ink = dark ? 'white' : 'black'
  const font = (size: number) => ({ family: 'Courier New, monospace', size, color: ink })
  const [lo, hi] = percentiles(plane.z, 0.01, 0.999)
  const xr = [plane.x[0], plane.x[plane.x.length - 1]]
  // centred on the arrival at the top of the band, where the cross is, with the sweep either side
  const sw = sweep.value
  const half = sw ? Math.max(5, 1.5 * (sw[1] - sw[0])) : 0
  const xView = sw ? [tz.plotTime((sw[0] - half) * 1000), tz.plotTime((sw[0] + half) * 1000)] : xr
  const inj = data.value?.injection
  Plotly.react(el, [
    { z: plane.z, x: plane.x, y: plane.dms, type: 'heatmap', colorscale: 'Viridis', showscale: false, zmin: lo, zmax: hi,
      hovertemplate: 'DM %{y:.1f}<br>S/N %{z:.1f}<extra></extra>' },
    { x: xr, y: [c.dm, c.dm], type: 'scatter', mode: 'lines',
      hoverinfo: 'skip', line: { dash: 'dash', width: 1, color: dark ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.7)' } },
    ...(inj ? [{ x: xr, y: [inj.dm, inj.dm], type: 'scatter', mode: 'lines', hoverinfo: 'skip',
      line: { dash: 'dot', width: 1.5, color: dark ? '#fbbf24' : '#b45309' } }] : [])
  ], {
    height: 520,
    margin: { t: 45, b: 55, l: 70, r: 20 },
    title: { text: 'DM-time plane', font: font(18) },
    xaxis: { title: { text: `Time (${tz.zoneName(d.dynspec_t[0] * 1000)})`, font: font(16) }, tickfont: { color: ink, family: 'Courier New, monospace' }, tickcolor: ink, nticks: 3, tickformat: '%H:%M:%S', range: xView },
    yaxis: { title: { text: 'DM (pc cm⁻³)', font: font(16) }, tickfont: { color: ink }, tickcolor: ink, range: [plane.dms[0], plane.dms[plane.dms.length - 1]] },
    paper_bgcolor: dark ? '#131826' : 'rgb(255,255,255)',
    plot_bgcolor: dark ? '#374151' : '#d1d5db',
    hovermode: 'closest', showlegend: false
  }, { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'] })
}

function drawAll() { drawBackground(); drawMain(); drawDmt() }

const clsTitle = computed(() => ({ candidate: 'Candidate', injection: 'Test injection', rfi: 'RFI', known: 'Known source' } as Record<string, string>)[cand.value?.cls ?? ''] ?? 'Candidate')
const clsColor: Record<string, string> = { candidate: 'amber', injection: 'sky', rfi: 'gray', known: 'violet' }
const fluenceText = (f: number) => f >= 1000 ? `${(f / 1000).toFixed(1)} Jy s` : `${f.toPrecision(3)} Jy ms`

watch(() => [props.node, props.id], load)
// moving the window only moves the axis, which keeps dragging smooth
watch(window_, w => {
  const el = mainDiv.value as any
  const r = w ?? span.value
  if (el?.data && r) Plotly.relayout(el, { 'xaxis.range': [tz.plotTime(r[0]), tz.plotTime(r[1])], 'xaxis.title.text': `Time (${tz.zoneName(r[0])})` })
  else drawMain()
})
watch(normOn, () => { prepare(); drawAll() })
watch([showTrack, dedispOn, colorMode, () => tz.mode.value], drawAll)
let ro: ResizeObserver | undefined
onMounted(() => {
  load()
  ro = new ResizeObserver(() => drawAll())
  for (const el of [mainDiv.value, dmtDiv.value]) if (el) ro.observe(el)
})
// the slider, and its canvas, appear once the data have loaded
watch(bg, (el, old) => {
  if (old) ro?.unobserve(old)
  if (el) { ro?.observe(el); drawBackground() }
})
onBeforeUnmount(() => {
  ro?.disconnect()
  for (const el of [mainDiv.value, dmtDiv.value]) if (el) Plotly.purge(el)
})
</script>

<template>
  <!-- one section of the viewer: summary, window, then the plots, divided by rules -->
  <div class="divide-y divide-gray-200 dark:divide-gray-800">
    <div class="pb-2 space-y-1">
      <div v-if="cand" class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <UBadge :color="clsColor[cand.cls] ?? 'amber'" variant="subtle" size="xs" :label="clsTitle" />
        <span v-if="cand.known_source?.kind == 'pulsar'">
          <SpectrogramSkymonPulsarName :name="cand.known_source.name" :alias="cand.known_source.alias" :size="22" />
        </span>
        <span v-else-if="cand.known_source" class="text-gray-500 dark:text-gray-400">{{ cand.known_source.name }}</span>
        <span class="tabular-nums">S/N {{ cand.snr.toFixed(1) }}</span>
        <span class="tabular-nums">DM {{ cand.dm.toFixed(1) }}<template v-if="cand.dm_step"> ± {{ (cand.dm_step / 2).toFixed(1) }}</template></span>
        <span class="tabular-nums">{{ cand.width_s.toFixed(2) }} s</span>
        <span v-if="cand.flux" class="tabular-nums">{{ fluenceText(cand.flux.fluence_jy_ms) }}</span>
        <span v-if="data?.injection" class="text-amber-600 dark:text-amber-400 tabular-nums">
          injected DM {{ data.injection.dm.toFixed(1) }}, S/N {{ data.injection.snr_target.toFixed(0) }}
        </span>
        <span v-if="cand.dm_arms?.length" class="text-gray-500 dark:text-gray-400"
          :title="cand.dm_arms.map(a => `DM ${a.dm.toFixed(1)}, S/N ${a.snr.toFixed(1)}`).join('; ')">
          {{ cand.dm_arms.length }} weaker at other DMs
        </span>
        <span v-if="cand.cls == 'rfi' && cand.rfi_reasons?.length" class="text-gray-500 dark:text-gray-400">{{ cand.rfi_reasons.join(', ') }}</span>
      </div>
      <div v-if="cand" class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400 tabular-nums">
        <span>RA {{ cand.ra.toFixed(2) }}°, Dec {{ cand.dec.toFixed(2) }}°, el {{ cand.el.toFixed(0) }}°</span>
        <span>{{ tz.dateTime(cand.t_inf * 1000) }} {{ tz.zoneName(cand.t_inf * 1000) }}<template v-if="sweep">, in band {{ tz.clock(sweep[0] * 1000) }}–{{ tz.clock(sweep[1] * 1000) }}</template></span>
      </div>
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 text-sm">
        <UCheckbox v-model="dedispOn" label="Dedispersed" />
        <UCheckbox v-model="showTrack" :label="dedispOn ? 'Arrival' : 'Dispersion curve'" />
        <UCheckbox v-model="normOn" label="Normalise" />
        <div class="flex-1" />
        <UButton size="xs" variant="outline" label="Live pixel" icon="i-heroicons-signal" @click="emit('live')" />
      </div>
    </div>

    <SpectrogramSkymonLoading v-if="pending" :key="id" :messages="[
      'Asking the monitor for the data kept with this candidate',
      'Reading its dynamic spectrum and DM-time plane',
      'Reading the 30 min of averages before it',
      'Drawing the candidate']" />
    <UAlert v-else-if="error" color="red" variant="soft" icon="i-heroicons-exclamation-triangle" :title="error" class="my-2" />

    <div v-show="data && !pending" class="py-2">
      <div class="flex items-center gap-2 mb-1 text-xs text-gray-500 dark:text-gray-400">
        <span>Window</span>
        <div class="flex-1" />
        <span>Before the burst</span>
        <USelect v-model="contextMin" size="2xs" :options="[{ label: '2 min', value: 2 }, { label: '10 min', value: 10 }, { label: '30 min', value: 30 }]" />
      </div>
      <SpectrogramTimeRangeSlider v-if="span" v-model="window_" :start="span[0]" :end="span[1]" :min-span-ms="3000"
        :height="56" seconds full-label="Whole span">
        <template #background>
          <canvas ref="bg" class="w-full h-full block" />
        </template>
      </SpectrogramTimeRangeSlider>
    </div>
    <div v-show="data && !pending" class="pt-2 grid grid-cols-1 2xl:grid-cols-3 gap-2">
      <div class="2xl:col-span-2 min-w-0"><div :id="mainId" ref="mainDiv" /></div>
      <div class="min-w-0"><div :id="dmtId" ref="dmtDiv" /></div>
    </div>
  </div>
</template>
