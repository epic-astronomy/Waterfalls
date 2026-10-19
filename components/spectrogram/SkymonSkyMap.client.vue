<script setup lang="ts">
// The sky one all-sky monitor sees, on its own HEALPix grid: the mean of the
// last 5 min of its accumulation, in an orthographic projection centred on
// the zenith at the end of that span (north up, east left, as seen looking
// up). It can be zoomed and panned; a click picks a pixel.
import { ang2pixZ, npix, pix2radec, pixDeg } from '~/lib/healpix'

interface SkyMap {
  node: string, nside: number, n: number, seconds: number, rows: number, interval_s: number,
  t_start: number | null, t_end: number | null, el_min: number,
  f_lo: number | null, f_hi: number | null, hpix_b64: string, values_b64: string
}
export interface Marker { ra: number, dec: number, color: string, title: string }

const props = defineProps<{
  node: string | null,
  selected?: number | null,
  markers?: Marker[],
  seconds?: number
}>()
const emit = defineEmits<{
  select: [p: { hpix: number, nside: number, ra: number, dec: number }],
  nside: [n: number | null]
}>()

const rtConfig = useRuntimeConfig()
const colorMode = useColorMode()
const tz = useTimeZone()

const LAT = 34.3484, LON = -106.8858  // LWA-SV
const D2R = Math.PI / 180
const BRIGHT = [
  { name: 'Cyg A', ra: 299.868, dec: 40.734 }, { name: 'Cas A', ra: 350.850, dec: 58.815 },
  { name: 'Tau A', ra: 83.633, dec: 22.014 }, { name: 'Vir A', ra: 187.706, dec: 12.391 },
  { name: 'Her A', ra: 252.784, dec: 4.993 }, { name: 'Hya A', ra: 139.524, dec: -12.096 }
]

const map = shallowRef<SkyMap | null>(null)
const pending = ref(false)
const error = ref('')
const stretch = useState<'asinh' | 'linear'>('skymon-map-stretch', () => 'asinh')
const showGrid = useState('skymon-map-grid', () => true)
const showLabels = useState('skymon-map-labels', () => true)
// the primary beam makes the sky fall off towards the horizon; flattening
// subtracts the median at each elevation (1° bins) so sources stand out
const flatten = useState('skymon-map-flatten', () => true)
let raw = new Float32Array(0)     // by HEALPix index, NaN where not tracked
let values = new Float32Array(0)  // as drawn
let tracked = new Int32Array(0)
let lo = 0, hi = 1

function lstDeg(unix: number) {
  const d = unix / 86400 + 2440587.5 - 2451545.0
  return ((280.46061837 + 360.98564736629 * d + LON) % 360 + 360) % 360
}

function prepare() {
  const m = map.value
  values = raw.slice()
  if (m && flatten.value && tracked.length) {
    // elevation of each tracked pixel at the end of the span, and the median in each 1° bin
    const ra0 = lstDeg(m.t_end ?? Date.now() / 1000), sd0 = Math.sin(LAT * D2R), cd0 = Math.cos(LAT * D2R)
    const els = new Float32Array(tracked.length)
    const bins: number[][] = Array.from({ length: 91 }, () => [])
    tracked.forEach((h, i) => {
      const [ra, dec] = pix2radec(m.nside, h)
      const d = dec * D2R
      const el = Math.asin(Math.sin(d) * sd0 + Math.cos(d) * cd0 * Math.cos((ra - ra0) * D2R)) / D2R
      els[i] = el
      const v = raw[h]
      if (v === v) bins[Math.max(0, Math.min(90, Math.floor(el)))].push(v)
    })
    const med = bins.map(b => { if (b.length < 5) return NaN; b.sort((a, c) => a - c); return b[b.length >> 1] })
    // bins with too few pixels (near the zenith, below the limit) take their neighbours' value
    for (let i = 89; i >= 0; i--) if (!(med[i] === med[i])) med[i] = med[i + 1]
    for (let i = 1; i <= 90; i++) if (!(med[i] === med[i])) med[i] = med[i - 1]
    tracked.forEach((h, i) => {
      // linear between bin centres
      const x = Math.max(0, Math.min(89.999, els[i] - 0.5)), k = Math.floor(x), f = x - k
      values[h] = raw[h] - (med[k] * (1 - f) + med[Math.min(90, k + 1)] * f)
    })
  }
  const s = Array.from(tracked, h => values[h]).filter(x => x === x).sort((a, b) => a - b)
  lo = s.length ? s[Math.floor((flatten.value ? 0.05 : 0.01) * (s.length - 1))] : 0
  hi = s.length ? s[Math.ceil(0.998 * (s.length - 1))] : 1
  if (!(hi > lo)) hi = lo + 1
}

async function load() {
  if (!props.node) { map.value = null; draw(); return }
  pending.value = true
  try {
    const m = await $fetch<SkyMap>(rtConfig.public.fastapiBase + `/skymon/${props.node}/skymap`,
      { query: { seconds: props.seconds ?? 300 } })
    const hp = new Int32Array(Uint8Array.from(atob(m.hpix_b64), c => c.charCodeAt(0)).buffer)
    const v = new Float32Array(Uint8Array.from(atob(m.values_b64), c => c.charCodeAt(0)).buffer)
    raw = new Float32Array(npix(m.nside)).fill(NaN)
    for (let i = 0; i < hp.length; i++) raw[hp[i]] = v[i]
    tracked = hp
    map.value = m
    prepare()
    error.value = ''
    emit('nside', m.nside)
  } catch (e: any) {
    error.value = e?.statusCode == 503 || e?.status == 503
      ? 'This monitor has no sky map yet.' : 'The sky map could not be loaded.'
    if (map.value?.node != props.node) { map.value = null; emit('nside', null) }
  } finally {
    pending.value = false
  }
  draw()
}

// view: (l, m) at the canvas centre and the scale in px per unit of l, m
const view = reactive({ l0: 0, m0: 0, zoom: 1 })
const wrap = ref<HTMLElement>()
const canvas = ref<HTMLCanvasElement>()
const size = ref(480)
let hpixBuf = new Int32Array(0)
let scale = 1, W = 0, H = 0, dpr = 1

function project(ra: number, dec: number, ra0: number, dec0: number) {
  const da = (ra - ra0) * D2R, d = dec * D2R, d0 = dec0 * D2R
  const n = Math.sin(d) * Math.sin(d0) + Math.cos(d) * Math.cos(d0) * Math.cos(da)
  return { l: Math.cos(d) * Math.sin(da), m: Math.sin(d) * Math.cos(d0) - Math.cos(d) * Math.sin(d0) * Math.cos(da), n }
}
const toScreen = (l: number, m: number) => [W / 2 - (l - view.l0) * scale, H / 2 - (m - view.m0) * scale]
const toLM = (sx: number, sy: number) => [view.l0 + (W / 2 - sx) / scale, view.m0 + (H / 2 - sy) / scale]

// Viridis, as on the spectrograms
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

let raf = 0
function draw() {
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(render)
}

function render() {
  const cv = canvas.value
  if (!cv) return
  const dark = colorMode.value == 'dark'
  dpr = Math.min(window.devicePixelRatio || 1, 1.5)
  W = Math.round(size.value * dpr); H = W
  if (cv.width != W) { cv.width = W; cv.height = H }
  scale = view.zoom * W / 2 * 0.94
  const ctx = cv.getContext('2d')!
  const img = ctx.createImageData(W, H)
  const px = img.data
  const bg = dark ? [19, 24, 38] : [255, 255, 255]
  const below = dark ? [31, 41, 55] : [229, 231, 235]
  const m = map.value
  if (hpixBuf.length != W * H) hpixBuf = new Int32Array(W * H)
  hpixBuf.fill(-1)
  const t = m?.t_end ?? Date.now() / 1000
  const ra0 = lstDeg(t), d0 = LAT * D2R, sd0 = Math.sin(d0), cd0 = Math.cos(d0)
  const nside = m?.nside ?? 0
  const k = stretch.value == 'asinh' ? 10 : 0, ak = Math.asinh(k)
  for (let y = 0; y < H; y++) {
    const mm = view.m0 + (H / 2 - y) / scale
    for (let x = 0; x < W; x++) {
      const l = view.l0 + (W / 2 - x) / scale
      const r2 = l * l + mm * mm
      const o = (y * W + x) * 4
      let c = bg
      if (r2 <= 1) {
        c = below
        if (nside) {
          const n = Math.sqrt(1 - r2)
          const z = mm * cd0 + n * sd0
          const phi = ra0 * D2R + Math.atan2(l, n * cd0 - mm * sd0)
          const hp = ang2pixZ(nside, Math.max(-1, Math.min(1, z)), phi)
          hpixBuf[y * W + x] = hp
          const v = values[hp]
          if (v === v) {
            let f = Math.max(0, Math.min(1, (v - lo) / (hi - lo)))
            if (k) f = Math.asinh(k * f) / ak
            const i = Math.round(f * 255) * 3
            px[o] = lut[i]; px[o + 1] = lut[i + 1]; px[o + 2] = lut[i + 2]; px[o + 3] = 255
            continue
          }
        }
      }
      px[o] = c[0]; px[o + 1] = c[1]; px[o + 2] = c[2]; px[o + 3] = 255
    }
  }
  // pixel edges once a pixel spans enough of the screen, and the selected pixel's outline
  const cellPx = nside ? scale * pixDeg(nside) * D2R : 0
  const grid = showGrid.value && cellPx > 16
  const sel = props.selected ?? -2
  for (let y = 0; y < H - 1; y++) {
    for (let x = 0; x < W - 1; x++) {
      const i = y * W + x, a = hpixBuf[i]
      if (a < 0) continue
      const r = hpixBuf[i + 1], b = hpixBuf[i + W]
      if (r == a && b == a) continue
      const o = i * 4
      if (a == sel || r == sel || b == sel) {
        px[o] = 255; px[o + 1] = 64; px[o + 2] = 64
      } else if (grid) {
        px[o] = px[o] * 0.7; px[o + 1] = px[o + 1] * 0.7; px[o + 2] = px[o + 2] * 0.7
      }
    }
  }
  ctx.putImageData(img, 0, 0)

  // horizon, elevation circles, compass and labels
  const ink = dark ? 'rgba(255,255,255,0.75)' : 'rgba(0,0,0,0.7)'
  const faint = dark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)'
  const [cx, cy] = toScreen(0, 0)
  ctx.lineWidth = dpr
  ctx.strokeStyle = ink
  ctx.beginPath(); ctx.arc(cx, cy, scale, 0, 2 * Math.PI); ctx.stroke()
  ctx.setLineDash([4 * dpr, 4 * dpr]); ctx.strokeStyle = faint
  for (const el of [30, 60]) { ctx.beginPath(); ctx.arc(cx, cy, scale * Math.cos(el * D2R), 0, 2 * Math.PI); ctx.stroke() }
  ctx.setLineDash([])
  ctx.font = `${12 * dpr}px ui-sans-serif, system-ui, sans-serif`
  ctx.fillStyle = ink
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  for (const [lab, l, mm] of [['N', 0, 1.04], ['S', 0, -1.04], ['E', 1.04, 0], ['W', -1.04, 0]] as const) {
    const [sx, sy] = toScreen(l, mm)
    ctx.fillText(lab, sx, sy)
  }
  const mark = (ra: number, dec: number) => {
    const p = project(ra, dec, ra0, LAT)
    return p.n > 0 ? toScreen(p.l, p.m) : null
  }
  if (showLabels.value) {
    ctx.font = `${11 * dpr}px ui-sans-serif, system-ui, sans-serif`
    ctx.textAlign = 'left'
    for (const s of BRIGHT) {
      const q = mark(s.ra, s.dec)
      if (!q) continue
      ctx.strokeStyle = 'rgba(255,255,255,0.9)'
      ctx.beginPath(); ctx.arc(q[0], q[1], 7 * dpr, 0, 2 * Math.PI); ctx.stroke()
      ctx.fillStyle = 'white'
      ctx.shadowColor = 'black'; ctx.shadowBlur = 3 * dpr
      ctx.fillText(s.name, q[0] + 9 * dpr, q[1] - 6 * dpr)
      ctx.shadowBlur = 0
    }
  }
  for (const mk of props.markers ?? []) {
    const q = mark(mk.ra, mk.dec)
    if (!q) continue
    ctx.strokeStyle = mk.color; ctx.lineWidth = 2 * dpr
    ctx.beginPath(); ctx.arc(q[0], q[1], 5 * dpr, 0, 2 * Math.PI); ctx.stroke()
    ctx.lineWidth = dpr
  }
}

// pointer: drag pans, the wheel zooms about the pointer, a click picks a pixel
const hover = ref<{ x: number, y: number, ra: number, dec: number, el: number, az: number, hpix: number, value: number } | null>(null)
let drag: { x: number, y: number, l0: number, m0: number, moved: boolean } | null = null
const ZMAX = 40
function clampView() {
  view.zoom = Math.max(1, Math.min(ZMAX, view.zoom))
  const lim = 1.05
  view.l0 = Math.max(-lim, Math.min(lim, view.l0))
  view.m0 = Math.max(-lim, Math.min(lim, view.m0))
}
function local(e: PointerEvent | WheelEvent | MouseEvent) {
  const r = canvas.value!.getBoundingClientRect()
  return [(e.clientX - r.left) * dpr, (e.clientY - r.top) * dpr, e.clientX - r.left, e.clientY - r.top]
}
function onDown(e: PointerEvent) {
  canvas.value!.setPointerCapture(e.pointerId)
  drag = { x: e.clientX, y: e.clientY, l0: view.l0, m0: view.m0, moved: false }
}
function onMove(e: PointerEvent) {
  const [sx, sy, cssx, cssy] = local(e)
  if (drag) {
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true
    if (drag.moved) {
      view.l0 = drag.l0 + dx * dpr / scale
      view.m0 = drag.m0 + dy * dpr / scale
      clampView(); draw()
    }
  }
  const i = Math.floor(sy) * W + Math.floor(sx)
  const hp = hpixBuf[i] ?? -1
  if (hp < 0 || !map.value) { hover.value = null; return }
  const [l, m] = toLM(sx, sy)
  const n = Math.sqrt(Math.max(0, 1 - l * l - m * m))
  const [ra, dec] = pix2radec(map.value.nside, hp)
  hover.value = { x: cssx, y: cssy, ra, dec, hpix: hp, value: raw[hp],
    el: Math.asin(n) / D2R, az: ((Math.atan2(l, m) / D2R) + 360) % 360 }
}
function onUp(e: PointerEvent) {
  const d = drag
  drag = null
  if (!d || d.moved || !map.value) return
  const [sx, sy] = local(e)
  const hp = hpixBuf[Math.floor(sy) * W + Math.floor(sx)] ?? -1
  if (hp < 0 || !(values[hp] === values[hp])) return
  const [ra, dec] = pix2radec(map.value.nside, hp)
  emit('select', { hpix: hp, nside: map.value.nside, ra, dec })
}
function zoomAt(sx: number, sy: number, f: number) {
  const [l, m] = toLM(sx, sy)
  const z = Math.max(1, Math.min(ZMAX, view.zoom * f))
  if (z == view.zoom) return
  view.zoom = z
  scale = view.zoom * W / 2 * 0.94
  // keep the point under the pointer in place
  view.l0 = l - (W / 2 - sx) / scale
  view.m0 = m - (H / 2 - sy) / scale
  clampView(); draw()
}
function onWheel(e: WheelEvent) {
  const [sx, sy] = local(e)
  zoomAt(sx, sy, Math.exp(-e.deltaY * 0.0015))
}
function zoomBy(f: number) { zoomAt(W / 2, H / 2, f) }
function resetView() { view.l0 = 0; view.m0 = 0; view.zoom = 1; draw() }
// centre on a position, zoomed in if the whole sky is shown
function centreOn(ra: number, dec: number) {
  const p = project(ra, dec, lstDeg(map.value?.t_end ?? Date.now() / 1000), LAT)
  if (p.n <= 0) return
  view.l0 = p.l; view.m0 = p.m
  if (view.zoom < 4) view.zoom = 4
  clampView(); draw()
}
defineExpose({ centreOn, reload: load })

let ro: ResizeObserver | undefined
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  ro = new ResizeObserver(es => {
    const w = es[0]?.contentRect.width ?? 0
    if (w > 0) { size.value = Math.round(Math.min(w, 620)); draw() }
  })
  if (wrap.value) ro.observe(wrap.value)
  load()
  timer = setInterval(load, 60000)
})
onBeforeUnmount(() => { ro?.disconnect(); clearInterval(timer); cancelAnimationFrame(raf) })
watch(() => props.node, () => { load() })
watch([() => props.selected, () => props.markers, stretch, showGrid, showLabels, colorMode], draw)
watch(flatten, () => { prepare(); draw() })

const spanText = computed(() => {
  const m = map.value
  if (!m?.t_start || !m.t_end) return ''
  return `Mean of ${tz.clock(m.t_start * 1000)} to ${tz.clock(m.t_end * 1000)} ${tz.zoneName(m.t_end * 1000)}, ` +
    `${m.f_lo?.toFixed(2)}–${m.f_hi?.toFixed(2)} MHz, nside ${m.nside}`
})
</script>

<template>
  <div class="space-y-2">
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
      <USelect v-model="stretch" size="xs" :options="[{ label: 'Asinh', value: 'asinh' }, { label: 'Linear', value: 'linear' }]" />
      <UCheckbox v-model="flatten" label="Flatten" title="Subtract the median at each elevation, which removes the fall of the primary beam towards the horizon" />
      <UCheckbox v-model="showGrid" label="Pixel grid" />
      <UCheckbox v-model="showLabels" label="Bright sources" />
      <div class="flex flex-1 justify-end">
      <UButton size="2xs" variant="ghost" icon="i-heroicons-plus" aria-label="Zoom in" @click="zoomBy(1.6)" />
      <UButton size="2xs" variant="ghost" icon="i-heroicons-minus" aria-label="Zoom out" @click="zoomBy(1 / 1.6)" />
      <UButton size="2xs" variant="ghost" icon="i-heroicons-arrows-pointing-out" aria-label="Whole sky" @click="resetView" />
      <UButton size="2xs" variant="ghost" icon="i-heroicons-arrow-path" aria-label="Reload" :loading="pending" @click="load" />
      </div>
    </div>
    <div ref="wrap" class="relative w-full">
      <canvas ref="canvas" class="block mx-auto touch-none select-none cursor-crosshair rounded"
        :style="{ width: size + 'px', height: size + 'px' }"
        @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp" @pointerleave="hover = null; drag = null"
        @wheel.prevent="onWheel" @dblclick="e => { const [sx, sy] = local(e); zoomAt(sx, sy, 2) }" />
      <div v-if="hover" class="pointer-events-none absolute z-10 rounded bg-gray-900/85 px-2 py-1 text-xs text-white tabular-nums"
        :style="{ left: Math.min(hover.x + 14, size - 170) + 'px', top: hover.y + 14 + 'px' }">
        <div>RA {{ hover.ra.toFixed(2) }}°, Dec {{ hover.dec.toFixed(2) }}°</div>
        <div>Elevation {{ hover.el.toFixed(1) }}°, azimuth {{ hover.az.toFixed(1) }}°</div>
        <div>HEALPix {{ hover.hpix }}<template v-if="hover.value === hover.value">, {{ hover.value.toPrecision(4) }}</template><template v-else>, not tracked</template></div>
      </div>
      <div v-if="!node || (!map && !pending)" class="absolute inset-0 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 pointer-events-none">
        {{ !node ? 'Select a monitor.' : error || 'No sky map.' }}
      </div>
    </div>
    <p class="text-xs text-gray-500 dark:text-gray-400">
      {{ spanText }}<template v-if="spanText">. </template>Drag to pan, scroll to zoom, click a pixel for its spectrogram.
      <span v-if="error && map" class="text-red-500">{{ error }}</span>
    </p>
  </div>
</template>
