<script setup lang="ts">
import type {  ImgSessionItem,  WatchListItem,  SessionQuery,  SpecgmQuery } from '~/types'
import { format } from 'date-fns';
const watchSource = ref<WatchListItem>()
const imgSession = ref<ImgSessionItem>()
const specgmQuery = ref<SpecgmQuery>()
const tabIndex = ref(0)

const tabItems = reactive([{
  label: 'Source',
  description: 'Select a source to continue',
  icon: 'i-material-symbols-view-list',
  slot: 'srcSelection',
  disabled: false
}, {
  label: 'Session',
  description: 'Select an observing session to continue',
  icon: 'i-material-symbols-date-range',
  slot: 'sessionSelection',
  disabled: false
}, {
  label: 'Visualization',
  description: 'Select a time window to view the Spectrograms',
  icon: 'i-material-symbols-key-visualizer',
  slot: 'visualization',
  disabled: false
}])

const obsStart = computed(() => {
  let ret = new Date()
  if (watchSource.value?.t_start) {
    let start = new Date(watchSource.value.t_start + 'Z')
    ret = start > new Date() ? new Date() : start
  }
  return format(ret.toISOString().slice(0, -1), "yyyy-MM-dd'T'HH:mm:ss")
})

const obsEnd = computed(() => {
  let ret = new Date()
  if (watchSource.value?.t_end) {
    let end_t = new Date(watchSource.value.t_end + 'Z')
    ret = end_t > new Date() ? new Date() : end_t
  }
  return format(ret.toISOString().slice(0, -1), "yyyy-MM-dd'T'HH:mm:ss")
})


function srcToSession() {
  tabItems[1].disabled = false
  tabIndex.value = 1
  sessionStart.value = obsStart.value
  sessionEnd.value = (new Date(new Date(obsStart.value + 'Z').getTime() + 3600 * 24 * 1000)).toISOString().slice(0, -1)

}


const sessionQuery = ref<SessionQuery>()
const sessionStart = ref('')
const sessionValidMsg = ref('')
const sessionEnd = ref('')


function fetchSession() {
  if (!watchSource?.value) return
  sessionQuery.value = { tStart: format(sessionStart.value, "yyyy-MM-dd'T'HH:mm:ss'Z'"), tEnd: format(sessionEnd.value, "yyyy-MM-dd'T'HH:mm:ss'Z'"), sourceName: watchSource.value.source }
}

const fetchSessionDisabled = computed(() => {
  let start = new Date(sessionStart.value + 'Z')
  let end = new Date(sessionEnd.value + 'Z')

  if (start > end) {
    sessionValidMsg.value = 'Start date cannot be greater than the end date.'
    return true
  }
  if ((end.getTime() - start.getTime()) / 1000 > 3600 * 24 * 30) {
    sessionValidMsg.value = 'Sessions can only be queried in windows of 30 days at a time.'
    return true
  }
  sessionValidMsg.value = ''
  return false
})

const selectedSessionStart=computed(()=>{
  let ret = new Date()
  if(imgSession?.value?.start_time){
    let start = new Date(imgSession.value.start_time + 'Z')
    ret = start > new Date() ? new Date() : start
  }
  return format(ret.toISOString().slice(0, -1), "yyyy-MM-dd'T'HH:mm:ss")
})

const selectedSessionEnd=computed(() => {
  let ret = new Date()
  if (imgSession.value?.end_time) {
    let end_t = new Date(imgSession.value.end_time + 'Z')
    ret = end_t > new Date() ? new Date() : end_t
  }
  return format(ret.toISOString().slice(0, -1), "yyyy-MM-dd'T'HH:mm:ss")
})

const specgmStart=ref('')
const specgmEnd=ref('')
const specgmValidMsg = ref('')
function sessionToVis() {
  tabItems[2].disabled = false
  tabIndex.value = 2
  specgmStart.value = selectedSessionStart.value
  specgmEnd.value = new Date(new Date(selectedSessionStart.value+'Z').getTime() + 120 * 1000).toISOString().slice(0, -1)
}

const fetchSpecgmDisabled = computed(() => {
  let start = new Date(specgmStart.value + 'Z')
  let end = new Date(specgmEnd.value + 'Z')

  if (start > end) {
    specgmValidMsg.value = 'Start date cannot be greater than the end date.'
    return true
  }
  if ((end.getTime() - start.getTime()) / 1000 > 120) {
    specgmValidMsg.value = 'Spectrogram duration cannot exceed 2 minutes.'
    return true
  }
  specgmValidMsg.value = ''
  return false
})

function fetchSpecgm(){
  if(!imgSession.value || !watchSource.value) return
  specgmQuery.value = {
    start_time: specgmStart.value,
        end_time: specgmEnd.value,
        session_id: imgSession.value.session_id,
        source_name:  watchSource.value.source,
        pixel_positions: '(0,0)',
        n_chan:imgSession.value.n_chan,
        n_pols:imgSession.value.n_pol,
        chan_bw_hz:imgSession.value.chan_bw_hz,
        start_chan: imgSession.value.chan0
  }
}

useSeoMeta({
  title: 'Spectrograms @ LWA-Sevilleta',
  ogTitle:  'Spectrograms @ LWA-Sevilleta',
  description: 'Explore spectrograms from the Long Wavelength Array, Sevilleta',
  ogDescription: 'Explore spectrograms from the Long Wavelength Array, Sevilleta'
})
</script>
<template>

  <UDashboardNavbar title="Spectrograms - Long Wavelength Array, Sevilleta"></UDashboardNavbar>
  <UDashboardPanelContent>
    <!-- <UDashboardCard> -->
    <UTabs :items="tabItems" v-model="tabIndex">
      <template #default="{ item, index, selected }">
        <div class="flex items-center gap-2 relative truncate">
          <UIcon :name="item.icon" class="w-4 h-4 flex-shrink-0" />

          <span class="truncate">{{ index + 1 }}. {{ item.label }}</span>

          <span v-if="selected" class="absolute -right-4 w-2 h-2 rounded-full bg-primary-500 dark:bg-primary-400" />
        </div>
      </template>
      <template #srcSelection="{ item }">
        <div class="flex flex-wrap justify-between items-center m-2">

          <span class="text-2xl">{{ item.description }}</span>
          <UButton label="Next" :disabled="watchSource?.source ? false : true" @click="srcToSession">
            <template #trailing>
              <UIcon name="i-heroicons-chevron-right" class="w-5 h-5" />
            </template>
          </UButton>
        </div>
        <SpectrogramWatchList v-model="watchSource" />
      </template>

      <template #sessionSelection="{ item }">
        <div v-if="watchSource">
          <div class="flex flex-wrap justify-between items-center m-2">

            <span class="text-2xl">{{ item.description }}</span>
            <div class="flex justify-between" orientation="horizontal">
              <UButtonGroup>

                <UButton label="Back" :disabled="watchSource?.source ? false : true" @click="tabIndex = 0">
                  <template #leading>
                    <UIcon name="i-heroicons-chevron-left" class="w-5 h-5" />
                  </template>
                </UButton>
                <UButton label="Next" :disabled="imgSession?.session_id ? false : true" @click="sessionToVis">
                  <template #trailing>
                    <UIcon name="i-heroicons-chevron-right" class="w-5 h-5" />
                  </template>
                </UButton>
              </UButtonGroup>
            </div>
          </div>
          <UCard :ui="{ body: { padding: 'px-2 py-2 sm:p-2 m-2' } }">
            <div class="flex flex-wrap justify-evenly items-center">

              <div class="flex flex-wrap justify-center items-center gap-2">
                <span class="text-md">Start time (UTC): </span>
                <UInput type="datetime-local" v-model="sessionStart" step=1 :min="obsStart" :max="obsEnd"></UInput>
              </div>

              <div class="flex flex-wrap justify-center items-center gap-2">
                <span class="text-md">End time (UTC): </span>
                <UInput type="datetime-local" v-model="sessionEnd" step=1 :min="obsStart" :max="obsEnd"></UInput>
              </div>


              <UButton :ui="{ rounded: 'rounded-md' }" variant="outline" label="Show Sessions" @click="fetchSession"
                :disabled="fetchSessionDisabled">
              </UButton>
            </div>
            <div v-if="sessionValidMsg" class="flex flex-wrap justify-center p-1">
              <UAlert :title="sessionValidMsg" color="red" icon="i-heroicons-exclamation-circle" variant="soft">
              </UAlert>
            </div>
          </UCard>
          <SpectrogramSessionList  :session-query="sessionQuery" v-model="imgSession" />
        </div>
        <div v-else="watchSource">
          <UCard>
            <UPageHero title="Please select a source before you can view sessions">
              <template #links>
                <UButton label="Go back" icon="i-heroicons-chevron-left" leading @click="tabIndex = 0"></UButton>
              </template>
            </UPageHero>
          </UCard>

        </div>
      </template>

      <template #visualization="{ item }">
        <div v-if="imgSession">
          <div class="flex justify-between items-center">
            <div class="text-2xl">{{ item.description }}</div>
            <UButton label="Back" @click="tabIndex--" :ui="{ rounded: 'rounded-md' }" icon="i-heroicons-chevron-left" leading></UButton>
          </div>
          <UCard :ui="{ body: { padding: 'px-2 py-2 sm:p-2 m-2' } }">
            <div class="flex flex-wrap justify-evenly items-center">

              <div class="flex flex-wrap justify-center items-center gap-2  sm:flex-rows-3">
                <span class="text-md">Start time (UTC): </span>
                <UInput type="datetime-local" v-model="specgmStart" step=1 :min="selectedSessionStart" :max="selectedSessionEnd"></UInput>
              </div>

              <div class="flex flex-wrap justify-center items-center gap-2">
                <span class="text-md">End time (UTC): </span>
                <UInput type="datetime-local" v-model="specgmEnd" step=1 :min="selectedSessionStart" :max="selectedSessionEnd"></UInput>
              </div>


              <UButton :ui="{ rounded: 'rounded-md' }" variant="outline" label="Display" @click="fetchSpecgm"
                :disabled="fetchSpecgmDisabled">
              </UButton>
            </div>
            <div v-if="specgmValidMsg" class="flex flex-wrap justify-center p-1">
              <UAlert :title="specgmValidMsg" color="red" icon="i-heroicons-exclamation-circle" variant="soft">
              </UAlert>
            </div>
          </UCard>
          <SpectrogramDisplay v-if="specgmQuery" :specgm-query="specgmQuery"></SpectrogramDisplay>
        </div>
        <div v-else="imgSession">


          <UPageHero title="Please select a session to explore spectrograms">
            <template #links>
              <UButton label="Go back" icon="i-heroicons-chevron-left" leading @click="tabIndex = 1"></UButton>
            </template>
          </UPageHero>

        </div>
      </template>
    </UTabs>
  </UDashboardPanelContent>
</template>
