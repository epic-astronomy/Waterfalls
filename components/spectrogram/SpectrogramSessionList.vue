<script setup lang="ts">

import type { PropType } from 'vue';
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
const coverageColumn = { key: 'coverage', label: 'Session and burst in the watch' }
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


const columns = [{
  key: 'start_time',
  label: 'Begin Time',
  sortable: true
}, {
  key: 'end_time',
  label: 'End Time',
  sortable: true
}, {
  key: 'chan0',
  label: 'Freq. (MHz)',
  sortable: true
}, {
  key: 'chan_bw_hz',
  label: 'Bandwidth (MHz)',
  sortable: true
}, {
  key: 'int_time',
  label: 'Time Resolution (ms)',
  sortable: true
},{
  key:'session_duration',
  label:'Session duration',
  sortable: true
}, {
  key: 'n_pol',
  label: '# Polarizations',
  sortable: true
},{
  key:'session_id',
  label: 'Session ID',
  sortable: true
}]

const selectedColumns = ref(columns.slice(0, 6))
const columnsTable = computed(() => {
  const shown = columns.filter((column) => selectedColumns.value.includes(column))
  if (!props.frb) return shown
  return [coverageColumn, ...shown.filter(c => c.key != 'start_time' && c.key != 'end_time')]
})
const selectedRow: Ref<ImgSessionItem[] | undefined> = ref([])

function rowSelect(row: ImgSessionItem) {
  if (selectedRow.value) {
    selectedRow.value.length = 0
    selectedRow.value.push(row)
    selectedSession.value = row
  }
}

const page = ref(1)
const rowsPerPage = ref(10)
const availrowsPerPage = [5, 10, 25]
const defaultImsSession: ImgSessions = { data: [], count: 0 }
const pageTotal = computed(() => imgSession.value.count)
const pageFrom = computed(() => Math.min((page.value - 1) * rowsPerPage.value + 1, pageTotal.value))
const pageTo = computed(() => Math.min(page.value * rowsPerPage.value, pageTotal.value))

// sort by a column; without one the newest sessions come first
const sort = ref<{ column: string, direction: 'asc' | 'desc' }>({ column: '', direction: 'asc' })

const { pending, data: imgSession, error: error } = await useLazyAsyncData<ImgSessions>(
  'sessionlist',
  () => $fetch(rtConfig.public.fastapiBase + '/imaging/sessions/',
    {
      query: {
        page: page.value,
        nrows: rowsPerPage.value,
        start_time: props.sessionQuery?.tStart,
        end_time: props.sessionQuery?.tEnd,
        source_name: props.sessionQuery?.sourceName,
        sort: sort.value.column || undefined,
        order: sort.value.direction,
        burst_only: props.frb && burstOnly.value ? true : undefined
      }
    }), {
  watch: [() => page.value, () => props.sessionQuery, rowsPerPage, sort, burstOnly],
  default: () => defaultImsSession
})

watch([() => props.sessionQuery, rowsPerPage, sort, burstOnly], () => {
  page.value = 1
})

watch(()=>error, (newError,_) => {
  if (newError) {
    toast.add({ title: 'Error fetching the session list', color: 'red', icon: 'i-heroicons-exclamation-circle' })
  }
})

const tableData = computed(() => {
  return imgSession.value.data ? imgSession.value.data : []
})

</script>
<template>
  <UCard class="w-full" :ui="{
    // base: '',
    // ring: '',
    divide: 'divide-y divide-gray-200 dark:divide-gray-700',
    header: { padding: 'px-4 py-5' },
    body: { padding: '', base: 'divide-y divide-gray-200 dark:divide-gray-700' },
    footer: { padding: 'p-4' }
  }">
    <div class="flex justify-between grid-cols-2 px-3 py-3.5 border-b border-gray-200 dark:border-gray-700">
      <div class="flex items-center gap-1.5">
        <span class="text-sm leading-5">Rows per page</span>
        <USelect v-model="rowsPerPage" :options="availrowsPerPage"></USelect>
        <slot name="toolbar" />
        <UCheckbox v-if="frb" v-model="burstOnly" label="Only sessions the burst crosses" class="ml-2" />
        <UButton v-if="sort.column" size="xs" color="gray" variant="ghost" icon="i-heroicons-arrow-uturn-left"
          label="Default order" @click="sort = { column: '', direction: 'asc' }" />
      </div>

      <USelectMenu v-model="selectedColumns" :options="columns" multiple>
        <UButton icon="i-heroicons-view-columns" color="gray" size="xs" class="w-40">
          Columns
        </UButton>
      </USelectMenu>
    </div>
    <UTable :rows="tableData" :loading="pending"
      :loading-state="{ icon: 'i-heroicons-arrow-path-20-solid', label: 'Loading...' }"
      :progress="{ color: 'primary', animation: 'carousel' }" :columns="columnsTable" @select="rowSelect"
      v-model="selectedRow" v-model:sort="sort" sort-mode="manual"
      :ui="{ checkbox: { padding: 'hidden' }, th: { base: 'text-center' }, td: { base: 'whitespace-nowrap text-center' } }"
      :empty-state="{ icon: 'i-heroicons-circle-stack-20-solid', label: 'No imaging sessions to show.' }">

      <template #coverage-data="{ row }">
        <svg v-if="coverage(row)" class="block h-7 min-w-48 w-full rounded-sm bg-gray-100 dark:bg-gray-800" viewBox="0 0 100 10"
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

      <template #start_time-data="{row}">
        {{ tz.dateTime(row.start_time) }} {{ tz.zoneName(row.start_time) }}
      </template>

      <template #end_time-data="{row}">
        {{ tz.dateTime(row.end_time) }} {{ tz.zoneName(row.end_time) }}
      </template>

      <template #chan0-data="{row}">
        {{ (row.chan0 * CHAN_BW_HZ / 1e6).toFixed(3) }}
      </template>

      <template #chan_bw_hz-data="{row}">
        {{ row.chan_bw_hz * row.n_chan/1e6 }}
      </template>

      <template #int_time-data="{row}">
        {{ (row.int_time * 1e3).toFixed(2) }}
      </template>

      <template #session_duration-data="{row}">
        {{humanizeDuration(new Date(row.end_time).getTime() - new Date(row.start_time).getTime(), { round: true })}}
      </template>
    </UTable>

    <template #footer>
      <div class="flex justify-between flex-wrap items-center">
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

        <UPagination :ui="{
          wrapper: 'flex items-center gap-1',
          rounded: '!rounded-full min-w-[32px] justify-center',
          default: {
            activeButton: {
              variant: 'outline'
            }
          }
        }" v-model="page" :page-count="rowsPerPage" :total="pageTotal" />
      </div>
    </template>

  </UCard>
</template>