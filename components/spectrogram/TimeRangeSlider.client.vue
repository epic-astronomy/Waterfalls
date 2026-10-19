<script setup lang="ts">
import type { PropType } from 'vue'

// A two-handle range slider over a light curve, for zooming a plot in time.
// Drag a handle to move one end, or the window between them to pan. The
// model is the selected [start, end] in UTC ms, or null for everything.
const range = defineModel<[number, number] | null>({ default: null })
const props = defineProps({
  times: { type: Array as PropType<number[]>, default: () => [] }, // UTC ms, ascending
  values: { type: Array as PropType<number[]>, default: () => [] }, // NaN for gaps
  minSpanMs: { type: Number, default: 5 * 60e3 },
  // labels to the second, for windows of minutes
  seconds: { type: Boolean, default: false },
  // the button that shows everything again
  fullLabel: { type: String, default: 'Full day' },
  // height of the track in px
  height: { type: Number, default: 42 },
  // the extent of the data, if wider than the curve's samples
  start: { type: Number, default: undefined },
  end: { type: Number, default: undefined }
})

const t0 = computed(() => props.start ?? props.times[0] ?? 0)
const t1 = computed(() => props.end ?? props.times[props.times.length - 1] ?? 1)
const span = computed(() => Math.max(1, t1.value - t0.value))
const sel = computed<[number, number]>(() => range.value ?? [t0.value, t1.value])
const frac = (t: number) => (t - t0.value) / span.value
const lo = computed(() => frac(sel.value[0]))
const hi = computed(() => frac(sel.value[1]))

// the light curve as SVG paths in a 1000 x 100 box, a line and the area
// under it, broken at gaps and clipped as below
const paths = computed(() => {
  const v = props.values.filter(isFinite).sort((a, b) => a - b)
  if (!v.length) return { line: '', area: '' }
  // the 2nd to 98th percentiles, and no more than 6 robust sigma from the
  // median, so a few deep dips do not flatten the rest even in short curves
  const med = v[Math.floor(v.length / 2)]
  const dev = v.map(x => Math.abs(x - med)).sort((a, b) => a - b)
  const sig = 1.4826 * dev[Math.floor(dev.length / 2)]
  let vmin = v[Math.floor(0.02 * (v.length - 1))], vmax = v[Math.ceil(0.98 * (v.length - 1))]
  if (sig > 0) { vmin = Math.max(vmin, med - 6 * sig); vmax = Math.min(vmax, med + 6 * sig) }
  const scale = vmax > vmin ? 80 / (vmax - vmin) : 0
  let line = '', area = '', run: string[] = []
  const close = () => {
    if (run.length) area += `M${run[0].split(',')[0]},100L${run.join('L')}L${run[run.length - 1].split(',')[0]},100Z`
    run = []
  }
  props.times.forEach((t, i) => {
    const y = props.values[i]
    if (!isFinite(y)) { close(); return }
    const pt = `${(1000 * frac(t)).toFixed(1)},${(90 - (Math.min(vmax, Math.max(vmin, y)) - vmin) * scale).toFixed(1)}`
    line += `${run.length ? 'L' : 'M'}${pt}`
    run.push(pt)
  })
  close()
  return { line, area }
})

function set(a: number, b: number) {
  const min = Math.min(props.minSpanMs, span.value)
  a = Math.max(t0.value, Math.min(a, t1.value - min))
  b = Math.min(t1.value, Math.max(b, a + min))
  range.value = a <= t0.value && b >= t1.value ? null : [a, b]
}

// pointer dragging of a handle or of the whole window
const track = ref<HTMLElement>()
let drag: { what: 'lo' | 'hi' | 'pan', x0: number, sel0: [number, number] } | null = null
const tAt = (clientX: number) => {
  const r = track.value!.getBoundingClientRect()
  return t0.value + span.value * Math.min(1, Math.max(0, (clientX - r.left) / r.width))
}
function start(e: PointerEvent, what: 'lo' | 'hi' | 'pan') {
  drag = { what, x0: e.clientX, sel0: [...sel.value] }
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  e.preventDefault()
}
function move(e: PointerEvent) {
  if (!drag) return
  const [a, b] = drag.sel0
  if (drag.what == 'lo') set(tAt(e.clientX), b)
  else if (drag.what == 'hi') set(a, tAt(e.clientX))
  else {
    const dt = (e.clientX - drag.x0) / track.value!.getBoundingClientRect().width * span.value
    const shift = Math.max(t0.value - a, Math.min(t1.value - b, dt))
    set(a + shift, b + shift)
  }
}
const end = () => { drag = null }
// a click on the track outside the window moves the nearer end there
function jump(e: PointerEvent) {
  const t = tAt(e.clientX)
  if (t < sel.value[0]) set(t, sel.value[1])
  else if (t > sel.value[1]) set(sel.value[0], t)
}
function key(e: KeyboardEvent, which: 'lo' | 'hi') {
  const stepMs = (e.shiftKey ? 0.1 : 0.01) * span.value
  const d = e.key == 'ArrowLeft' || e.key == 'ArrowDown' ? -stepMs : e.key == 'ArrowRight' || e.key == 'ArrowUp' ? stepMs : 0
  if (!d) return
  e.preventDefault()
  if (which == 'lo') set(sel.value[0] + d, sel.value[1])
  else set(sel.value[0], sel.value[1] + d)
}

// labels in the time zone chosen on the page
const tz = useTimeZone()
const hhmm = (t: number) => props.seconds ? tz.clock(t) : tz.clock(t).slice(0, 5)
</script>

<template>
  <div class="select-none">
    <div ref="track" :style="{ height: height + 'px' }" class="relative rounded-md bg-gray-50 dark:bg-gray-800/60 ring-1 ring-gray-200 dark:ring-gray-700 touch-none"
      @pointerdown.self="jump">
      <!-- anything drawn under the window, in the same time span as the track -->
      <div class="absolute inset-0 overflow-hidden rounded-md pointer-events-none"><slot name="background" :t0="t0" :t1="t1" /></div>
      <svg class="absolute inset-0 h-full w-full pointer-events-none" viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">
        <path :d="paths.area" class="fill-primary-500/15 dark:fill-primary-400/20" />
        <path :d="paths.line" fill="none" vector-effect="non-scaling-stroke" stroke-width="1.5" class="stroke-primary-600 dark:stroke-primary-400" />
      </svg>
      <!-- outside the window -->
      <div class="absolute inset-y-0 left-0 bg-gray-400/30 dark:bg-gray-950/60 rounded-l-md pointer-events-none" :style="{ width: `${100 * lo}%` }" />
      <div class="absolute inset-y-0 right-0 bg-gray-400/30 dark:bg-gray-950/60 rounded-r-md pointer-events-none" :style="{ width: `${100 * (1 - hi)}%` }" />
      <!-- the window -->
      <div class="absolute inset-y-0 border-y-2 border-primary-500 dark:border-primary-400 cursor-grab active:cursor-grabbing"
        :style="{ left: `${100 * lo}%`, width: `${100 * (hi - lo)}%` }"
        @pointerdown="start($event, 'pan')" @pointermove="move" @pointerup="end" @pointercancel="end" />
      <div v-for="h in (['lo', 'hi'] as const)" :key="h" role="slider" tabindex="0"
        :aria-label="h == 'lo' ? 'Start of the zoom window' : 'End of the zoom window'"
        :aria-valuemin="t0" :aria-valuemax="t1" :aria-valuenow="h == 'lo' ? sel[0] : sel[1]"
        :aria-valuetext="hhmm(h == 'lo' ? sel[0] : sel[1]) + ' ' + tz.zoneName(sel[0])"
        class="absolute inset-y-0 -ml-1.5 w-3 rounded-sm bg-primary-500 dark:bg-primary-400 cursor-ew-resize flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-300"
        :style="{ left: `${100 * (h == 'lo' ? lo : hi)}%` }"
        @pointerdown="start($event, h)" @pointermove="move" @pointerup="end" @pointercancel="end" @keydown="key($event, h)">
        <span class="h-4 w-px bg-white/80 dark:bg-gray-900/80" />
      </div>
    </div>
    <div class="mt-1 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
      <span>{{ hhmm(t0) }}</span>
      <span class="flex items-center gap-2">
        <span class="font-medium text-gray-700 dark:text-gray-200">{{ hhmm(sel[0]) }} to {{ hhmm(sel[1]) }} {{ tz.zoneName(sel[0]) }}</span>
        <UButton v-if="range" size="2xs" color="gray" variant="ghost" :label="fullLabel" @click="range = null" />
      </span>
      <span>{{ hhmm(t1) }}</span>
    </div>
  </div>
</template>
