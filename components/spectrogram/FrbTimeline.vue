<script setup lang="ts">
import type { PropType } from 'vue'
import type { ImgSessionItem, WatchListItem } from '~/types'
import { CHAN_BW_HZ } from '~/lib/ndp'
import { arrivalMs, frbParams, freqAtMs, utcMs } from '~/lib/frb'

// Clickable timeline of an FRB imaging session. Each cell is one spectrogram
// window. Cells reached by the dispersed burst in this band are highlighted,
// with a mark for the part of the band the burst is in, and the daily digest
// Stokes I is drawn as a bar under each cell.
const props = defineProps({
  watchSource: { type: Object as PropType<WatchListItem>, required: true },
  imgSession: { type: Object as PropType<ImgSessionItem>, required: true },
  windowStart: { type: String, default: '' },
  windowEnd: { type: String, default: '' }
})
const emit = defineEmits<{ select: [start: string, end: string], clear: [] }>()

const rtConfig = useRuntimeConfig()
const tz = useTimeZone()

const CELL_S = 180 // the longest spectrogram window, the long-integration cadence
const CELLS_PER_ROW = 20 // one hour per row
const ROW_S = CELL_S * CELLS_PER_ROW

const isoUtc = (ms: number) => new Date(ms).toISOString().slice(0, 19)
const hhmmss = (ms: number) => tz.clock(ms)
const overlaps = (a0: number, a1: number, b0: number, b1: number) => a0 < b1 && b0 < a1

const session = computed(() => ({
  start: utcMs(String(props.imgSession.start_time)),
  end: Math.min(utcMs(String(props.imgSession.end_time)), Date.now())
}))

const band = computed(() => {
  const fLo = props.imgSession.chan0 * CHAN_BW_HZ / 1e6
  return { fLo, fHi: fLo + props.imgSession.n_chan * props.imgSession.chan_bw_hz / 1e6 }
})

const frb = computed(() => frbParams(props.watchSource))

// Arrival across the band, from its top to its bottom edge, widened by the
// DM uncertainty
const burst = computed(() => {
  const p = frb.value
  if (!p) return null
  return {
    start: arrivalMs(p, band.value.fHi, p.dm - p.dmErr),
    end: arrivalMs(p, band.value.fLo, p.dm + p.dmErr)
  }
})

// The burst's track through the band within a cell: x is the fraction of the
// cell's time and y the fraction of the band from its top
function subBand(c0: number, c1: number) {
  const p = frb.value
  if (!p) return null
  const { fLo, fHi } = band.value
  const tTop = Math.max(c0, arrivalMs(p, fHi))
  const tBot = Math.min(c1, arrivalMs(p, fLo))
  if (tTop >= tBot) return null
  const fTop = freqAtMs(p, tTop)
  const fBot = freqAtMs(p, tBot)
  const x = (t: number) => (t - c0) / (c1 - c0)
  const y = (f: number) => (fHi - f) / (fHi - fLo)
  return { x1: x(tTop), y1: y(fTop), x2: x(tBot), y2: y(fBot), fTop, fBot }
}

const { data: lightCurve } = await useLazyAsyncData<{ img_time: string, stokes_i: number[] }[]>(
  'frb-lightcurve',
  () => $fetch(rtConfig.public.fastapiBase + '/imaging/lightcurve/', {
    query: {
      start_time: isoUtc(session.value.start),
      end_time: isoUtc(session.value.end),
      source_name: props.watchSource.source,
      chan0: props.imgSession.chan0
    }
  }),
  { watch: [() => props.imgSession.session_id], default: () => [] }
)

const median = (a: number[]) => {
  const s = a.filter(isFinite).sort((x, y) => x - y)
  return s.length ? s[Math.floor(s.length / 2)] : NaN
}

// Median-over-channel Stokes I of each digest point, scaled to 0-1 between
// the 2nd and 98th percentiles of the session
const levels = computed(() => {
  const pts = (lightCurve.value ?? []).map(d => ({ t: utcMs(d.img_time), v: median(d.stokes_i) })).filter(d => isFinite(d.v))
  if (!pts.length) return []
  const sorted = pts.map(d => d.v).sort((x, y) => x - y)
  const lo = sorted[Math.floor(0.02 * (sorted.length - 1))]
  const hi = sorted[Math.ceil(0.98 * (sorted.length - 1))]
  return pts.map(d => ({ t: d.t, v: hi > lo ? Math.min(1, Math.max(0, (d.v - lo) / (hi - lo))) : 0.5 }))
})

function levelIn(t0: number, t1: number) {
  const vs = levels.value.filter(d => d.t >= t0 && d.t < t1).map(d => d.v)
  return vs.length ? vs.reduce((a, b) => a + b) / vs.length : null
}

const shown = computed(() => props.windowStart && props.windowEnd
  ? { start: utcMs(props.windowStart), end: utcMs(props.windowEnd) }
  : null)

// Rows start on the hour so the labels read as clock times
const rows = computed(() => {
  const { start, end } = session.value
  const out = []
  for (let r = Math.floor(start / (ROW_S * 1e3)) * ROW_S * 1e3; r < end; r += ROW_S * 1e3) {
    const cells = []
    for (let i = 0; i < CELLS_PER_ROW; i++) {
      const c0 = r + i * CELL_S * 1e3
      const c1 = c0 + CELL_S * 1e3
      const inBurst = !!burst.value && overlaps(c0, c1, burst.value.start, burst.value.end)
      cells.push({
        id: c0,
        t0: Math.max(c0, start),
        t1: Math.min(c1, end),
        inSession: overlaps(c0, c1, start, end),
        // the cells where the session starts and ends, marked on their outer edge
        isStart: start >= c0 && start < c1,
        isEnd: end > c0 && end <= c1,
        before: c1 <= start,
        inBurst,
        sub: inBurst ? subBand(c0, c1) : null,
        level: levelIn(c0, c1),
        isShown: !!shown.value && overlaps(c0, c1, shown.value.start, shown.value.end)
      })
    }
    out.push({ id: r, label: hhmmss(r).slice(0, 5), cells })
  }
  return out
})

const sessionCells = computed(() => rows.value.flatMap(r => r.cells).filter(c => c.inSession))

const select = (c: { t0: number, t1: number }) => emit('select', isoUtc(c.t0), isoUtc(c.t1))

// Open each session on the first cell the burst reaches. When it never
// reaches this band during the session there is nothing to show until a cell
// is picked, so clear the previous spectrogram.
watch(() => props.imgSession.session_id, () => {
  const c = sessionCells.value.find(c => c.inBurst)
  if (c) select(c)
  else emit('clear')
}, { immediate: true })

// Left and right arrows step through the cells
function onKey(e: KeyboardEvent) {
  if (e.key != 'ArrowLeft' && e.key != 'ArrowRight') return
  if (e.target instanceof HTMLElement && e.target.closest('input, textarea, select, [contenteditable="true"]')) return
  const cells = sessionCells.value
  const cur = cells.findIndex(c => c.isShown)
  const next = cells[cur + (e.key == 'ArrowRight' ? 1 : -1)]
  if (cur < 0 || !next) return
  e.preventDefault()
  select(next)
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

const burstNote = computed(() => {
  const p = frb.value
  const b = burst.value
  if (!p || !b) return 'No DM in the VOEvent, so the burst arrival cannot be marked.'
  const sweep = `At DM ${p.dm.toFixed(1)} ± ${p.dmErr.toFixed(1)} pc cm⁻³ the burst crosses ${band.value.fHi.toFixed(2)}–${band.value.fLo.toFixed(2)} MHz between ${hhmmss(b.start)} and ${hhmmss(b.end)} ${tz.zoneName(b.start)}`
  if (b.end < session.value.start) return `${sweep}, before this session started. Pick a cell to view the session.`
  if (b.start > session.value.end) return `${sweep}, after this session ended. Pick a cell to view the session.`
  return `${sweep}.`
})

function cellTitle(c: (typeof sessionCells.value)[number]) {
  if (!c.inSession) return c.before ? 'Before the session started' : 'After the session ended'
  let t = `${hhmmss(c.t0)}–${hhmmss(c.t1)} ${tz.zoneName(c.t0)}`
  if (c.sub) t += ` · burst at ${c.sub.fTop.toFixed(2)}–${c.sub.fBot.toFixed(2)} MHz`
  else if (c.inBurst) t += ' · burst arrival (DM uncertainty)'
  return t
}

// Cells outside the session keep their place in the hour as dashed outlines,
// so a session that starts late in an hour does not leave a puzzling gap
function cellClass(c: { inSession: boolean, inBurst: boolean, isShown: boolean }) {
  if (!c.inSession) return 'border border-dashed border-gray-300 dark:border-gray-700 cursor-default'
  return [
    c.inBurst
      ? 'bg-amber-300 hover:bg-amber-400 dark:bg-amber-500/70 dark:hover:bg-amber-500/90'
      : 'bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600',
    c.isShown ? 'ring-2 ring-primary-500 dark:ring-primary-400 ring-offset-1 ring-offset-white dark:ring-offset-gray-900' : ''
  ]
}
</script>

<template>
  <UCard :ui="{ body: { padding: 'px-2 py-2 sm:p-3' } }">
    <div class="flex flex-wrap items-center justify-between gap-2 mb-2 text-sm">
      <span>Session timeline, {{ CELL_S / 60 }} min per cell <span class="text-gray-500 dark:text-gray-400">(← → to step)</span></span>
      <UButton :to="`/waterfalls/spectrograms/frb?event=${watchSource.id}`"
        trailing-icon="i-heroicons-arrow-right-20-solid" size="sm" color="primary" variant="solid" label="Show all bands, dedispersed" />
    </div>
    <div class="space-y-1.5">
      <!-- minutes past the hour -->
      <div class="flex items-end gap-2" aria-hidden="true">
        <span class="w-11 shrink-0" />
        <div class="grid flex-1 gap-0.5" :style="{ gridTemplateColumns: `repeat(${CELLS_PER_ROW}, minmax(0, 1fr))` }">
          <span v-for="k in CELLS_PER_ROW" :key="k" class="text-[10px] font-mono text-gray-400 dark:text-gray-500 leading-none">
            {{ (k - 1) % 5 == 0 ? `:${String((k - 1) * CELL_S / 60).padStart(2, '0')}` : '' }}
          </span>
        </div>
      </div>
      <div v-for="row in rows" :key="row.id" class="flex items-start gap-2">
        <span class="w-11 shrink-0 pt-1 text-xs font-mono text-gray-500 dark:text-gray-400">{{ row.label }}</span>
        <div class="grid flex-1 gap-0.5" :style="{ gridTemplateColumns: `repeat(${CELLS_PER_ROW}, minmax(0, 1fr))` }">
          <div v-for="c in row.cells" :key="c.id" class="flex flex-col gap-0.5">
            <button type="button" class="relative h-7 rounded-sm overflow-hidden transition-colors"
              :class="cellClass(c)" :disabled="!c.inSession" :title="cellTitle(c)"
              :aria-label="`Show ${cellTitle(c)}`" @click="select(c)">
              <svg v-if="c.sub" class="absolute inset-0 w-full h-full" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
                <line :x1="c.sub.x1" :y1="c.sub.y1" :x2="c.sub.x2" :y2="c.sub.y2" vector-effect="non-scaling-stroke"
                  stroke-width="2" stroke-linecap="round" class="stroke-amber-800 dark:stroke-amber-100" />
              </svg>
              <span v-if="c.inSession && c.isStart" class="absolute inset-y-0 left-0 w-1 bg-primary-500 dark:bg-primary-400" />
              <span v-if="c.inSession && c.isEnd" class="absolute inset-y-0 right-0 w-1 bg-primary-500 dark:bg-primary-400" />
            </button>
            <div class="h-3 flex items-end" :class="c.inSession ? '' : 'invisible'">
              <div v-if="c.level !== null" class="w-full rounded-sm bg-primary-500/70"
                :style="{ height: `max(1px, ${c.level * 100}%)` }" />
            </div>
          </div>
        </div>
      </div>
    </div>
    <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">{{ burstNote }}</p>
  </UCard>
</template>
