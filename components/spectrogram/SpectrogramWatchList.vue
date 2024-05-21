<script setup lang="ts">

import type { WatchListItem, WatchList } from '~/types'
const toast = useToast()
const rtConfig = useRuntimeConfig()
const watchSource = defineModel({
  type: Object as PropType<WatchListItem>,
  required: false
})

const columns = [{
  key: 'source',
  label: 'Source Name'
}, {
  key: 'watch_status',
  label: 'Status'
}, {
  key: 't_start',
  label: 'Monitoring Start'
}, {
  key: 't_end',
  label: 'Monitoring End'
}, {
  key: 'reason',
  label: 'Reason'
}, {
  key: 'author',
  label: 'Author'
}, {
  key: 'ra_deg',
  label: 'RA'
}, {
  key: 'dec_deg',
  label: 'DEC'
}]

const selectedColumns = ref(columns.slice(0, 4))
const columnsTable = computed(() => columns.filter((column) => selectedColumns.value.includes(column)))
const selectedRow: Ref<WatchListItem[] | undefined> = ref([])

function rowSelect(row: WatchListItem) {
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

const { pending, data: watchlist, error: error } = await useLazyAsyncData<WatchList>(
  'watchlist',
  () => $fetch(rtConfig.public.fastapiBase + '/watchlist/watching/?page=' + page.value + '&nrows=' + rowsPerPage.value), {
  watch: [() => page.value],
  default: () => defaultWatchList
})

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
    <div class="flex justify-between grid-cols-2 px-3 py-3.5 border-b border-gray-200 dark:border-gray-700">
      <div class="flex items-center gap-1.5">
        <span class="text-sm leading-5"> Rows per page:</span>
        <USelect v-model="rowsPerPage" :options="availrowsPerPage"></USelect>
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
      v-model="selectedRow" :ui="{ checkbox: { padding: 'hidden' } }">

      <template #watch_status-data="{ row }">
        <UBadge variant="soft" :label="row.watch_status == 'watching' ? 'Watching' : 'Completed'"
          :color="row.watch_status == 'watching' ? 'primary' : 'orange'" size="xs"></UBadge>
      </template>

      <template #t_start-data="{row}">
        {{ new Date(row.t_start+'Z').toUTCString() }}
      </template>

      <template #t_end-data="{row}">
      {{ row.watch_status=='watching' && row.watch_mode=='continuous' ? '-' :  new Date(row.t_end+'Z').toUTCString() }}</template>
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