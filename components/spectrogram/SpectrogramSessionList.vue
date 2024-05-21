<script setup lang="ts">

import type { PropType } from 'vue';
import type { ImgSessionItem, ImgSessions, SessionQuery } from '~/types'
import humanizeDuration from 'humanize-duration'
const toast = useToast()
const rtConfig = useRuntimeConfig()
const selectedSession = defineModel({
  type: Object as PropType<ImgSessionItem>,
  required: false
})

const props = defineProps({
  sessionQuery: {
    type: Object as PropType<SessionQuery>,
    required: false
  }
})


const columns = [{
  key: 'start_time',
  label: 'Begin Time'
}, {
  key: 'end_time',
  label: 'End Time'
}, {
  key: 'chan0',
  label: 'Freq. (MHz)'
}, {
  key: 'chan_bw_hz',
  label: 'Bandwidth (MHz)'
}, {
  key: 'int_time',
  label: 'Time Resolution (ms)'
},{
  key:'session_duration',
  label:'Session duration'
}, {
  key: 'n_pol',
  label: '# Polarizations'
},{
  key:'session_id',
  label: 'Session ID'
}]

const selectedColumns = ref(columns.slice(0, 6))
const columnsTable = computed(() => columns.filter((column) => selectedColumns.value.includes(column)))
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

const { pending, data: imgSession, error: error } = await useLazyAsyncData<ImgSessions>(
  'sessionlist',
  () => $fetch(rtConfig.public.fastapiBase + '/imaging/sessions/',
    {
      query: {
        page: page.value,
        nrows: rowsPerPage.value,
        start_time: props.sessionQuery?.tStart,
        end_time: props.sessionQuery?.tEnd,
        source_name: props.sessionQuery?.sourceName
      }
    }), {
  watch: [() => page.value,()=>props.sessionQuery],
  default: () => defaultImsSession
})

watch(()=>props.sessionQuery,(newQuery, oldQuery)=>{
  page.value=1
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
        <span class="text-sm leading-5"> Rows per page:</span>
        <USelect v-model="rowsPerPage" :options="availrowsPerPage"></USelect>
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
      v-model="selectedRow" :ui="{ checkbox: { padding: 'hidden' } }"
      :empty-state="{ icon: 'i-heroicons-circle-stack-20-solid', label: 'No imaging sessions to show.' }">

      <template #start_time-data="{row}">
        {{ new Date(row.start_time+'Z').toUTCString() }}
      </template>

      <template #end_time-data="{row}">
        {{ new Date(row.end_time+'Z').toUTCString() }}
      </template>

      <template #chan0-data="{row}">
        {{ row.chan0 * 25000/1e6 }}
      </template>

      <template #chan_bw_hz-data="{row}">
        {{ row.chan_bw_hz * row.n_chan/1e6 }}
      </template>

      <template #int_time-data="{row}">
        {{ row.int_time * 1e3 }}
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