<script setup lang="ts">
import type { PropType } from 'vue'
import type { DropdownMenuItem, TableColumn } from '@nuxt/ui'
import type { ImgSessionItem, ImgSessions, SessionQuery } from '~/types'
import humanizeDuration from 'humanize-duration'
import { CHAN_BW_HZ } from '~/lib/ndp'
import { arrivalMs, utcMs, type FrbParams } from '~/lib/frb'
const toast = useToast()
const tz = useTimeZone()
const rtConfig = useRuntimeConfig()
const selectedSession = defineModel({
  type: Object as PropType<ImgSessionItem>,
  required: false
})

const props = defineProps({
  sessionQuery: {
    type: Object as PropType<SessionQuery>,
    required: false
  },
  // for a CHIME/FRB source: its DM and arrival, and the span of its watch
  frb: { type: Object as PropType<FrbParams | null>, default: null },
  watchWindow: { type: Array as unknown as PropType<[number, number] | null>, default: null }
})

// For an FRB the exact times matter less than whether a session catches the
// burst, so the time columns give way to a strip spanning the whole watch:
// time across and the session's band down, top edge at the top. The session
// is shaded and the burst drawn as its dispersion curve through the band,
// bright where the session records it
const burstOnly = ref(false)
function coverage(row: ImgSessionItem) {
  const p = props.frb, w = props.watchWindow
  if (!p || !w) return null
  const span = Math.max(1, w[1] - w[0])
  const pos = (t: number) => Math.min(100, Math.max(0, 100 * (t - w[0]) / span))
  const fLo = row.chan0 * CHAN_BW_HZ / 1e6
  const fHi = fLo + row.n_chan * row.chan_bw_hz / 1e6
  const s0 = utcMs(String(row.start_time)), s1 = utcMs(String(row.end_time))
  const b0 = arrivalMs(p, fHi, Math.max(0, p.dm - p.dmErr)), b1 = arrivalMs(p, fLo, p.dm + p.dmErr)
  const hit = s0 < b1 && s1 > b0
  // the curve at the CHIME DM, in a 100 x 10 box
  const n = 24
  const curve = Array.from({ length: n + 1 }, (_, k) => {
    const f = fHi - (fHi - fLo) * k / n
    return `${k ? 'L' : 'M'}${pos(arrivalMs(p, f)).toFixed(3)},${(10 * k / n).toFixed(3)}`
  }).join('')
  return {
    id: `cov-${row.session_id}-${row.chan0}`,
    session: { left: pos(s0), width: Math.max(0.5, pos(s1) - pos(s0)) },
    curve,
    hit,
    title: `Session ${tz.clock(s0)} to ${tz.clock(s1)}, burst crosses the band ${tz.clock(b0)} to ${tz.clock(b1)} ${tz.zoneName(b0)}`
      + (hit ? '' : '. The session misses the burst.')
  }
}


const columns = [
  { key: 'start_time', label: 'Begin Time' },
  { key: 'end_time', label: 'End Time' },
  { key: 'chan0', label: 'Freq. (MHz)' },
  { key: 'chan_bw_hz', label: 'Bandwidth (MHz)' },
  { key: 'int_time', label: 'Time Resolution (ms)' },
  { key: 'session_duration', label: 'Session duration' },
  { key: 'n_pol', label: '# Polarizations' },
  { key: 'session_id', label: 'Session ID' }
]

const shown = ref(columns.slice(0, 6).map(c => c.key))
const columnItems = computed<DropdownMenuItem[]>(() => columns.map(c => ({
  label: c.label, type: 'checkbox' as const, checked: shown.value.includes(c.key),
  onUpdateChecked: (on: boolean) => { shown.value = on ? columns.map(x => x.key).filter(k => k == c.key || shown.value.includes(k)) : shown.value.filter(k => k != c.key) },
  onSelect: (e: Event) => e.preventDefault()
})))
const columnsTable = computed<TableColumn<ImgSessionItem>[]>(() => {
  const cols: TableColumn<ImgSessionItem>[] = columns.filter(c => shown.value.includes(c.key))
    .filter(c => !props.frb || (c.key != 'start_time' && c.key != 'end_time'))
    .map(c => ({ id: c.key, accessorKey: c.key, header: sortHeader(sort, c.key, c.label) }))
  return props.frb ? [{ id: 'coverage', header: 'Session and burst in the watch' }, ...cols] : cols
})

// every click, even on the row already selected, so the page can move on
const emit = defineEmits<{ picked: [row: ImgSessionItem] }>()
function rowSelect(row: ImgSessionItem) {
  emit('picked', row)
  selectedSession.value = row
}

// Rows share the height left in the window, so a page of rows fills it
// without scrolling; never below the compact height of 37 px
const ROW_MIN_PX = 37, ROW_MAX_PX = 80
const tableBox = ref<HTMLElement>()
const footerBox = ref<HTMLElement>()
const rowPx = ref(ROW_MIN_PX)
function fitRows() {
  const el = tableBox.value
  if (!el || !el.offsetParent) return
  const body = el.querySelector('tbody')
  if (!body) return
  const scroller = el.closest('.overflow-y-auto')
  const viewBottom = scroller ? scroller.getBoundingClientRect().bottom : window.innerHeight
  const footer = (footerBox.value?.offsetHeight ?? 40) + 32 // the card footer and its padding
  const space = viewBottom - body.getBoundingClientRect().top - footer - 24 + (scroller?.scrollTop ?? 0)
  rowPx.value = Math.max(ROW_MIN_PX, Math.min(ROW_MAX_PX, Math.floor(space / rowsPerPage.value)))
}
const fitObserver = import.meta.client ? new ResizeObserver(() => fitRows()) : null
watch(tableBox, (el, old) => { if (old) fitObserver?.unobserve(old); if (el) fitObserver?.observe(el) })
onMounted(() => window.addEventListener('resize', fitRows))
onBeforeUnmount(() => { window.removeEventListener('resize', fitRows); fitObserver?.disconnect() })

const page = ref(1)
const rowsPerPage = ref(10)
const availrowsPerPage = [5, 10, 25]
const defaultImsSession: ImgSessions = { data: [], count: 0 }
const pageTotal = computed(() => imgSession.value.count)
const pageFrom = computed(() => Math.min((page.value - 1) * rowsPerPage.value + 1, pageTotal.value))
const pageTo = computed(() => Math.min(page.value * rowsPerPage.value, pageTotal.value))

// sort by a column; without one the newest sessions come first
const sort = ref<ManualSort>({ column: '', direction: 'asc' })

const listQuery = (pg: number) => ({
  page: pg,
  nrows: rowsPerPage.value,
  start_time: props.sessionQuery?.tStart,
  end_time: props.sessionQuery?.tEnd,
  source_name: props.sessionQuery?.sourceName,
  sort: sort.value.column || undefined,
  order: sort.value.direction,
  burst_only: props.frb && burstOnly.value ? true : undefined
})
const { pending, data: imgSession, error: error } = await useLazyAsyncData<ImgSessions>(
  'sessionlist',
  () => $fetch(rtConfig.public.fastapiBase + '/imaging/sessions/', { query: listQuery(page.value) }), {
  watch: [() => page.value, () => props.sessionQuery, rowsPerPage, sort, burstOnly],
  default: () => defaultImsSession
})

watch([() => props.sessionQuery, rowsPerPage, sort, burstOnly], () => {
  page.value = 1
})

watch(()=>error, (newError,_) => {
  if (newError) {
    toast.add({ title: 'Error fetching the session list', color: 'error', icon: 'i-heroicons-exclamation-circle' })
  }
})

watch([() => imgSession.value.data, rowsPerPage], () => nextTick(fitRows))

// The table shows the selected session as selected however it was chosen,
// including from the page's address, and turns to its page if needed
const isSelected = (r: ImgSessionItem, sel?: ImgSessionItem) => !!sel && r.session_id == sel.session_id && r.chan0 == sel.chan0
const tableMeta = { class: { tr: (row: { original: ImgSessionItem }) => 'cursor-pointer h-(--row-h) ' + (isSelected(row.original, selectedSession.value) ? selectedRowClass : '') } }
let seeking = false
watch([selectedSession, () => imgSession.value.data, pending], async ([sel]) => {
  if (!sel || !props.sessionQuery || seeking || pending.value || (imgSession.value.data ?? []).some((r: ImgSessionItem) => isSelected(r, sel))) return
  seeking = true
  try {
    for (let pg = 1; pg <= 20; pg++) {
      const r = await $fetch<ImgSessions>(rtConfig.public.fastapiBase + '/imaging/sessions/', { query: listQuery(pg) })
      if (r.data.some((x: ImgSessionItem) => isSelected(x, sel))) { if (page.value != pg) page.value = pg; break }
      if (pg * rowsPerPage.value >= r.count) break
    }
  } finally { seeking = false }
})

const tableData = computed(() => {
  return imgSession.value.data ? imgSession.value.data : []
})

</script>
<template>
  <UCard class="w-full" :ui="{ header: 'px-4 py-5', body: 'p-0 sm:p-0', footer: 'p-4 sm:p-4' }">
    <div class="flex justify-between grid-cols-2 px-3 py-3.5 border-b border-default">
      <div class="flex items-center gap-1.5">
        <span class="text-sm leading-5">Rows per page</span>
        <USelect v-model="rowsPerPage" :items="availrowsPerPage" class="w-20" />
        <slot name="toolbar" />
        <UCheckbox v-if="frb" v-model="burstOnly" label="Only sessions the burst crosses" class="ml-2" />
        <UButton v-if="sort.column" size="xs" color="neutral" variant="ghost" icon="i-heroicons-arrow-uturn-left"
          label="Default order" @click="sort = { column: '', direction: 'asc' }" />
      </div>

      <UDropdownMenu :items="columnItems" :content="{ align: 'end' }">
        <UButton icon="i-heroicons-view-columns" color="neutral" variant="outline" size="xs" class="w-40" label="Columns" />
      </UDropdownMenu>
    </div>
    <div ref="tableBox">
    <UTable :data="tableData" :columns="columnsTable" :loading="pending" loading-color="primary" loading-animation="carousel"
      :meta="tableMeta" :ui="{ th: 'text-center px-4 py-3', td: 'whitespace-nowrap text-center px-4 py-2' }" class="my-0"
      :style="{ '--row-h': `${rowPx}px` }" empty="No imaging sessions to show."
      @select="(_e: Event, row: { original: ImgSessionItem }) => rowSelect(row.original)">

      <template #coverage-cell="{ row: { original: row } }">
        <svg v-if="coverage(row)" class="block h-5 min-w-48 w-full rounded-sm bg-gray-100 dark:bg-gray-800" viewBox="0 0 100 10"
          preserveAspectRatio="none" role="img" :aria-label="coverage(row)!.title">
          <title>{{ coverage(row)!.title }}</title>
          <defs>
            <clipPath :id="coverage(row)!.id">
              <rect :x="coverage(row)!.session.left" y="0" :width="coverage(row)!.session.width" height="10" />
            </clipPath>
          </defs>
          <rect :x="coverage(row)!.session.left" y="0" :width="coverage(row)!.session.width" height="10"
            class="fill-primary-500/30 dark:fill-primary-400/25" />
          <path :d="coverage(row)!.curve" fill="none" vector-effect="non-scaling-stroke" stroke-width="1.5" stroke-linecap="round"
            class="stroke-amber-500/40 dark:stroke-amber-300/40" />
          <path :d="coverage(row)!.curve" fill="none" vector-effect="non-scaling-stroke" stroke-width="2.5" stroke-linecap="round"
            :clip-path="`url(#${coverage(row)!.id})`" class="stroke-amber-500 dark:stroke-amber-300" />
        </svg>
      </template>

      <template #start_time-cell="{ row: { original: row } }">
        {{ tz.dateTime(row.start_time) }} {{ tz.zoneName(row.start_time) }}
      </template>

      <template #end_time-cell="{ row: { original: row } }">
        {{ tz.dateTime(row.end_time) }} {{ tz.zoneName(row.end_time) }}
      </template>

      <template #chan0-cell="{ row: { original: row } }">
        {{ (row.chan0 * CHAN_BW_HZ / 1e6).toFixed(3) }}
      </template>

      <template #chan_bw_hz-cell="{ row: { original: row } }">
        {{ row.chan_bw_hz * row.n_chan/1e6 }}
      </template>

      <template #int_time-cell="{ row: { original: row } }">
        {{ (row.int_time * 1e3).toFixed(2) }}
      </template>

      <template #session_duration-cell="{ row: { original: row } }">
        {{humanizeDuration(new Date(row.end_time).getTime() - new Date(row.start_time).getTime(), { round: true })}}
      </template>
    </UTable>
    </div>

    <template #footer>
      <div ref="footerBox" class="flex justify-between flex-wrap items-center">
        <div>
          <span class="text-sm leading-5">
            Showing
            <span class="font-medium">{{ pageFrom }}</span>
            to
            <span class="font-medium">{{ pageTo }}</span>
            of
            <span class="font-medium">{{ pageTotal }}</span>
            sessions
          </span>
        </div>

        <UPagination v-model:page="page" :items-per-page="rowsPerPage" :total="pageTotal" active-variant="outline"
          :ui="{ list: 'gap-1', item: 'rounded-full min-w-8 justify-center', first: 'rounded-full', prev: 'rounded-full', next: 'rounded-full', last: 'rounded-full' }" />
      </div>
    </template>

  </UCard>
</template>