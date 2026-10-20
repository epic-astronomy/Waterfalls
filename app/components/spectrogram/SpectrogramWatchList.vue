<script setup lang="ts">
import type { DropdownMenuItem, TableColumn } from '@nuxt/ui'
import type { WatchListItem, WatchList } from '~/types'
const toast = useToast()
const tz = useTimeZone()
const rtConfig = useRuntimeConfig()
const watchSource = defineModel({
  type: Object as PropType<WatchListItem>,
  required: false
})
// a calendar day in the chosen time zone; only sources watched that day are listed
const props = defineProps({ day: { type: String as PropType<string | null>, default: null } })
const dayRange = computed(() => props.day ? tz.dayRange(props.day) : null)

// the columns, of which the first six are shown at first
const columns = [
  { key: 'source', label: 'Source Name' },
  { key: 'origin', label: 'Origin' },
  { key: 'category', label: 'Type' },
  { key: 'watch_status', label: 'Observation Status' },
  { key: 't_start', label: 'Monitoring Start' },
  { key: 't_end', label: 'Monitoring End' },
  { key: 'reason', label: 'Reason' },
  { key: 'author', label: 'Author' },
  { key: 'ra_deg', label: 'RA' },
  { key: 'dec_deg', label: 'DEC' }
]

const shown = ref(columns.slice(0, 6).map(c => c.key))
const columnItems = computed<DropdownMenuItem[]>(() => columns.map(c => ({
  label: c.label, type: 'checkbox' as const, checked: shown.value.includes(c.key),
  onUpdateChecked: (on: boolean) => { shown.value = on ? columns.map(x => x.key).filter(k => k == c.key || shown.value.includes(k)) : shown.value.filter(k => k != c.key) },
  onSelect: (e: Event) => e.preventDefault()
})))

// What EPIC did during the watch, from the imaging sessions (data_status):
// a watch can be active or over while EPIC was not running
function observationStatus(row: WatchListItem & { origin?: string, data_status?: string }) {
  if (row.watch_status == 'watching')
    return row.data_status == 'not_recording' ? { label: 'Not recording', color: 'warning' } : { label: 'Active', color: 'primary' }
  if (row.origin != 'chime') return { label: 'Inactive', color: 'neutral' }
  return row.data_status == 'not_observed' ? { label: 'Not observed', color: 'error' } : { label: 'Completed', color: 'notice' }
}

// every click, even on the row already selected, so the page can move on
const emit = defineEmits<{ picked: [row: WatchListItem] }>()
function rowSelect(row: WatchListItem) {
  emit('picked', row)
  watchSource.value = row
}



const defaultWatchList: WatchList = { data: [], count: 0 }
// Pagination
const page = ref(1)
const rowsPerPage = ref(10)
const availrowsPerPage = [5, 10, 25]
const pageTotal = computed(() => watchlist.value.count)
const pageFrom = computed(() => Math.min((page.value - 1) * rowsPerPage.value + 1, pageTotal.value))
const pageTo = computed(() => Math.min(page.value * rowsPerPage.value, pageTotal.value))

// Filter by kind of source, and sort by a column. Without a sort column the
// server lists what is being watched first, then the most recently added.
const categories = [
  { value: 'all', label: 'All' },
  { value: 'frb', label: 'FRBs' },
  { value: 'pulsar', label: 'Pulsars' },
  { value: 'solar_system', label: 'Solar system' }
]
const category = ref('all')
const sort = ref<ManualSort>({ column: '', direction: 'asc' })
const columnsTable = computed<TableColumn<WatchListItem>[]>(() => columns.filter(c => shown.value.includes(c.key))
  .map(c => ({ accessorKey: c.key, header: sortHeader(sort, c.key, c.label) })))
const categoryLabels: Record<string, string> = { frb: 'FRB', pulsar: 'Pulsar', solar_system: 'Solar system', other: 'Other' }

const listQuery = (pg: number) => ({
  page: pg,
  nrows: rowsPerPage.value,
  category: category.value,
  sort: sort.value.column || undefined,
  order: sort.value.direction,
  active_from: dayRange.value ? dayRange.value[0] + 'Z' : undefined,
  active_to: dayRange.value ? dayRange.value[1] + 'Z' : undefined
})
const { pending, data: watchlist, error: error } = await useLazyAsyncData<WatchList>(
  'watchlist',
  () => $fetch(rtConfig.public.fastapiBase + '/watchlist/all/', { query: listQuery(page.value) }), {
  watch: [page, rowsPerPage, category, sort, dayRange],
  default: () => defaultWatchList
})

watch([rowsPerPage, category, sort, dayRange], () => { page.value = 1 })

watch(error, (newError) => {
  if (newError) {
    toast.add({ title: 'Error fetching the watchlist', color: 'error', icon: 'i-heroicons-exclamation-circle' })
  }
})

// The table shows the selected source as selected however it was chosen,
// including from the page's address, and turns to its page if needed
const tableMeta = { class: { tr: (row: { original: WatchListItem }) => 'cursor-pointer ' + (row.original.id == watchSource.value?.id ? selectedRowClass : '') } }
let seeking = false
watch([watchSource, () => watchlist.value.data, pending], async ([sel]) => {
  if (!sel || seeking || pending.value || (watchlist.value.data ?? []).some((r: WatchListItem) => r.id == sel.id)) return
  seeking = true
  try {
    for (let pg = 1; pg <= 20; pg++) {
      const r = await $fetch<WatchList>(rtConfig.public.fastapiBase + '/watchlist/all/', { query: listQuery(pg) })
      if (r.data.some((x: WatchListItem) => x.id == sel.id)) { if (page.value != pg) page.value = pg; break }
      if (pg * rowsPerPage.value >= r.count) break
    }
  } finally { seeking = false }
})

const tableData = computed(() => {
  return watchlist.value.data ? watchlist.value.data : []
})

</script>
<template>
  <UCard class="w-full" :ui="{ header: 'px-4 py-5', body: 'p-0 sm:p-0', footer: 'p-4 sm:p-4' }">
    <div class="flex flex-wrap justify-between items-center gap-3 px-3 py-3.5 border-b border-default">
      <div class="flex items-center gap-1.5">
        <span class="text-sm leading-5">Rows per page</span>
        <USelect v-model="rowsPerPage" :items="availrowsPerPage" class="w-20" />
        <slot name="toolbar" />
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <UFieldGroup size="xs">
          <UButton v-for="c in categories" :key="c.value" :label="c.label"
            :color="category == c.value ? 'primary' : 'neutral'" :variant="category == c.value ? 'solid' : 'ghost'"
            @click="category = c.value" />
        </UFieldGroup>
        <UButton v-if="sort.column" size="xs" color="neutral" variant="ghost" icon="i-heroicons-arrow-uturn-left"
          label="Default order" @click="sort = { column: '', direction: 'asc' }" />
      </div>

      <UDropdownMenu :items="columnItems" :content="{ align: 'end' }">
        <UButton icon="i-heroicons-view-columns" color="neutral" variant="outline" size="xs" class="w-40" label="Columns" />
      </UDropdownMenu>
    </div>
    <UTable :data="tableData" :columns="columnsTable" :loading="pending" loading-color="primary" loading-animation="carousel"
      :meta="tableMeta" class="my-0" @select="(_e: Event, row: { original: WatchListItem }) => rowSelect(row.original)">

      <template #origin-cell="{ row }">
        <UBadge variant="soft" size="md" :color="row.original.origin == 'chime' ? 'info' : 'neutral'"
          :label="row.original.origin == 'chime' ? 'CHIME/FRB' : 'Manual'" />
      </template>

      <template #category-cell="{ row }">
        {{ categoryLabels[row.original.category ?? ''] ?? row.original.category }}
      </template>

      <template #watch_status-cell="{ row }">
        <UBadge variant="soft" :label="observationStatus(row.original).label" :color="observationStatus(row.original).color" size="md" />
      </template>

      <template #t_start-cell="{ row }">
        {{ tz.dateTime(row.original.t_start) }} {{ tz.zoneName(row.original.t_start) }}
      </template>

      <template #t_end-cell="{ row }">
        {{ row.original.watch_status == 'watching' && row.original.watch_mode == 'continuous' ? '' : `${tz.dateTime(row.original.t_end)} ${tz.zoneName(row.original.t_end)}` }}
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
            sources
          </span>
        </div>

        <UPagination v-model:page="page" :items-per-page="rowsPerPage" :total="pageTotal" active-variant="outline"
          :ui="{ list: 'gap-1', item: 'rounded-full min-w-8 justify-center', first: 'rounded-full', prev: 'rounded-full', next: 'rounded-full', last: 'rounded-full' }" />
      </div>
    </template>
  </UCard>
</template>
