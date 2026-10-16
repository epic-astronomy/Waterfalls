<script setup lang="ts">

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

const columns = [{
  key: 'source',
  label: 'Source Name',
  sortable: true
}, {
  key: 'origin',
  label: 'Origin',
  sortable: true
}, {
  key: 'category',
  label: 'Type',
  sortable: true
}, {
  key: 'watch_status',
  label: 'Observation Status',
  sortable: true
}, {
  key: 't_start',
  label: 'Monitoring Start',
  sortable: true
}, {
  key: 't_end',
  label: 'Monitoring End',
  sortable: true
}, {
  key: 'reason',
  label: 'Reason',
  sortable: true
}, {
  key: 'author',
  label: 'Author',
  sortable: true
}, {
  key: 'ra_deg',
  label: 'RA',
  sortable: true
}, {
  key: 'dec_deg',
  label: 'DEC',
  sortable: true
}]

const selectedColumns = ref(columns.slice(0, 6))
const columnsTable = computed(() => columns.filter((column) => selectedColumns.value.includes(column)))
const selectedRow: Ref<WatchListItem[] | undefined> = ref([])

// every click, even on the row already selected, so the page can move on
const emit = defineEmits<{ picked: [row: WatchListItem] }>()
function rowSelect(row: WatchListItem) {
  emit('picked', row)
  if (selectedRow.value) {
    selectedRow.value.length = 0
    selectedRow.value.push(row)
    watchSource.value = row
  }
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
const sort = ref<{ column: string, direction: 'asc' | 'desc' }>({ column: '', direction: 'asc' })
const categoryLabels: Record<string, string> = { frb: 'FRB', pulsar: 'Pulsar', solar_system: 'Solar system', other: 'Other' }

const { pending, data: watchlist, error: error } = await useLazyAsyncData<WatchList>(
  'watchlist',
  () => $fetch(rtConfig.public.fastapiBase + '/watchlist/all/', {
    query: {
      page: page.value,
      nrows: rowsPerPage.value,
      category: category.value,
      sort: sort.value.column || undefined,
      order: sort.value.direction,
      active_from: dayRange.value ? dayRange.value[0] + 'Z' : undefined,
      active_to: dayRange.value ? dayRange.value[1] + 'Z' : undefined
    }
  }), {
  watch: [page, rowsPerPage, category, sort, dayRange],
  default: () => defaultWatchList
})

watch([rowsPerPage, category, sort, dayRange], () => { page.value = 1 })

watch(error, (newError) => {
  if (newError) {
    toast.add({ title: 'Error fetching the watchlist', color: 'red', icon: 'i-heroicons-exclamation-circle' })
  }
})

const tableData = computed(() => {
  return watchlist.value.data ? watchlist.value.data : []
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
    <div class="flex flex-wrap justify-between items-center gap-3 px-3 py-3.5 border-b border-gray-200 dark:border-gray-700">
      <div class="flex items-center gap-1.5">
        <span class="text-sm leading-5">Rows per page</span>
        <USelect v-model="rowsPerPage" :options="availrowsPerPage"></USelect>
        <slot name="toolbar" />
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <UButtonGroup size="xs">
          <UButton v-for="c in categories" :key="c.value" :label="c.label"
            :color="category == c.value ? 'primary' : 'gray'" :variant="category == c.value ? 'solid' : 'ghost'"
            @click="category = c.value" />
        </UButtonGroup>
        <UButton v-if="sort.column" size="xs" color="gray" variant="ghost" icon="i-heroicons-arrow-uturn-left"
          label="Default order" @click="sort = { column: '', direction: 'asc' }" />
      </div>

      <USelectMenu v-model="selectedColumns" :options="columns" multiple :truncate="false">
        <UButton icon="i-heroicons-view-columns" color="gray" size="xs" class="w-40">
          Columns
        </UButton>
      </USelectMenu>
    </div>
    <UTable :rows="tableData" :loading="pending"
      :loading-state="{ icon: 'i-heroicons-arrow-path-20-solid', label: 'Loading...' }"
      :progress="{ color: 'primary', animation: 'carousel' }" :columns="columnsTable" @select="rowSelect"
      v-model="selectedRow" v-model:sort="sort" sort-mode="manual" :ui="{ checkbox: { padding: 'hidden' } }">

      <template #origin-data="{ row }">
        <UBadge variant="soft" size="xs" :color="row.origin == 'chime' ? 'blue' : 'gray'"
          :label="row.origin == 'chime' ? 'CHIME/FRB' : 'Manual'" />
      </template>

      <template #category-data="{ row }">
        {{ categoryLabels[row.category] ?? row.category }}
      </template>

      <template #watch_status-data="{ row }">
        <UBadge variant="soft" :label="row.watch_status == 'watching' ? 'Active' : row.origin == 'chime' ? 'Completed' : 'Inactive'"
          :color="row.watch_status == 'watching' ? 'primary' : row.origin == 'chime' ? 'orange' : 'gray'" size="xs"></UBadge>
      </template>

      <template #t_start-data="{row}">
        {{ tz.dateTime(row.t_start) }} {{ tz.zoneName(row.t_start) }}
      </template>

      <template #t_end-data="{row}">
      {{ row.watch_status=='watching' && row.watch_mode=='continuous' ? '' : `${tz.dateTime(row.t_end)} ${tz.zoneName(row.t_end)}` }}</template>
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