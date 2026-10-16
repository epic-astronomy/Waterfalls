<script setup lang="ts">
import type {  ImgSessionItem,  ImgSessions,  WatchListItem,  SessionQuery,  SpecgmQuery } from '~/types'
import { format } from 'date-fns';
import { frbParams, isFrbSource } from '~/lib/frb'
import { CHAN_BW_HZ } from '~/lib/ndp'
const watchSource = ref<WatchListItem>()
const imgSession = ref<ImgSessionItem>()
const specgmQuery = ref<SpecgmQuery>()
// the tab from the address, so a reload opens it directly
const tabIndex = ref(Math.max(0, Math.min(2, Number(useRoute().query.tab) || 0)))
// FRB sessions pick their windows on the timeline instead of the time inputs
const isFrb = computed(() => isFrbSource(watchSource.value))
const frb = computed(() => frbParams(watchSource.value))
// The window inputs show the chosen time zone; the values stay in UTC
const tz = useTimeZone()
const inZone = (r: Ref<string>) => computed({ get: () => tz.toInput(r.value), set: (v: string) => { r.value = tz.fromInput(v) } })

const tabItems = reactive([{
  label: 'Source',
  description: 'Select a source to continue',
  icon: 'i-material-symbols-view-list',
  slot: 'srcSelection',
  disabled: false
}, {
  label: 'Session',
  description: 'Select an observing session for ',
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




// Source tab: a day on the calendar lists the sources watched that day, and
// days with a CHIME/FRB trigger are marked
const rtConfig = useRuntimeConfig()
const listDay = ref<string | null>(null)
const markRange = ref<[string, string] | null>(null)
const { data: frbTimes } = await useLazyAsyncData<{ time: string }[]>('frb-days', () => markRange.value
  ? $fetch(rtConfig.public.fastapiBase + '/watchlist/events/', {
    query: { start: tz.dayRange(markRange.value[0])[0] + 'Z', end: tz.dayRange(markRange.value[1])[1] + 'Z', category: 'frb' }
  })
  : Promise.resolve([]), { watch: [markRange, tz.mode], default: () => [], server: false })
const frbDays = computed(() => {
  const out: Record<string, number> = {}
  for (const e of frbTimes.value ?? []) { const k = tz.dayKey(e.time); out[k] = (out[k] ?? 0) + 1 }
  return out
})

// Session tab: every session of the watch, or those of one day
const sessionQuery = ref<SessionQuery>()
const sessionDay = ref<string | null>(null)
// the whole watch, to the present while it continues
const watchWindow = computed<[number, number] | null>(() => watchSource.value
  ? [Date.parse(obsStart.value + 'Z'), Date.parse(obsEnd.value + 'Z')] : null)
const watchFirstDay = computed(() => tz.dayKey(obsStart.value))
const watchLastDay = computed(() => tz.dayKey(obsEnd.value))

function fetchSession() {
  if (!watchSource?.value) return
  const [start, end] = sessionDay.value ? tz.dayRange(sessionDay.value) : [obsStart.value, obsEnd.value]
  sessionQuery.value = { tStart: start + 'Z', tEnd: end + 'Z', sourceName: watchSource.value.source }
}
watch([sessionDay, tz.mode], fetchSession)

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
const specgmStartInput = inZone(specgmStart)
const specgmEndInput = inZone(specgmEnd)
// The tabs are the only navigation, so the defaults the Next buttons used to
// set are set when a source or a session is selected instead.
// A new source: all its sessions over the whole watch, newest first, on the
// Session tab. Long watches such as the Sun's can be narrowed with the time
// filter there.
watch(watchSource, (src) => {
  if (!src) return
  imgSession.value = undefined
  specgmQuery.value = undefined
  // the day picked on the Source tab carries over, if the source was watched then
  const day = !isFrb.value && listDay.value && listDay.value >= watchFirstDay.value && listDay.value <= watchLastDay.value
    ? listDay.value : null
  if (sessionDay.value != day) sessionDay.value = day // fetches through the watcher
  else fetchSession()
  if (!restoring) tabIndex.value = 1
})

// A new session: the first 3 minutes, unless the FRB timeline chooses the window
watch(imgSession, (session) => {
  if (!session) return
  if (!restoring) tabIndex.value = 2
  if (isFrb.value) return
  specgmQuery.value = undefined
  specgmStart.value = selectedSessionStart.value
  specgmEnd.value = new Date(new Date(selectedSessionStart.value + 'Z').getTime() + 180 * 1000).toISOString().slice(0, -1)
})

const fetchSpecgmDisabled = computed(() => {
  let start = new Date(specgmStart.value + 'Z')
  let end = new Date(specgmEnd.value + 'Z')

  if (start > end) {
    specgmValidMsg.value = 'Start date cannot be greater than the end date.'
    return true
  }
  if ((end.getTime() - start.getTime()) / 1000 > 180) {
    specgmValidMsg.value = 'Spectrogram duration cannot exceed 3 minutes.'
    return true
  }
  specgmValidMsg.value = ''
  return false
})

// a window restored from the address, used in place of the first window the
// FRB timeline picks by itself (or of the default 3 minutes otherwise)
let pendingWindow: [string, string] | null = null
function takePendingWindow() { const w = pendingWindow; pendingWindow = null; return w }

function clearSpecgmWindow() {
  const w = takePendingWindow()
  if (w) return selectSpecgmWindow(w[0], w[1])
  specgmStart.value = ''
  specgmEnd.value = ''
  specgmQuery.value = undefined
}

function selectSpecgmWindow(start: string, end: string) {
  const w = takePendingWindow()
  if (w) [start, end] = w
  specgmStart.value = start
  specgmEnd.value = end
  fetchSpecgm()
}

function fetchSpecgm(){
  if(!imgSession.value || !watchSource.value) return
  specgmQuery.value = {
    start_time: specgmStart.value,
        end_time: specgmEnd.value,
        // session_id: imgSession.value.session_id,
        chan0: imgSession.value.chan0,
        source_name:  watchSource.value.source,
        pixel_positions: '(0,0)',
        n_chan:imgSession.value.n_chan,
        n_pols:imgSession.value.n_pol,
        chan_bw_hz:imgSession.value.chan_bw_hz,
        start_chan: imgSession.value.chan0
  }
}

// The header bar shows the current selection instead of a title (the sidebar
// names the page); each part opens its tab
// The selection lives in the address (?source, session, band, from, to,
// tab), so leaving the page, for the FRB events page say, and coming back,
// reloading or sharing the link reopens the same source, session and window
const route = useRoute()
const router = useRouter()
let restoring = false
async function restoreFromAddress() {
  const q = route.query
  const id = Number(q.source)
  if (!id) return
  restoring = true
  try {
    watchSource.value = await $fetch<WatchListItem>(rtConfig.public.fastapiBase + `/watchlist/source/${id}`)
    await nextTick()
    if (q.session && q.band != null) {
      const found = await $fetch<ImgSessions>(rtConfig.public.fastapiBase + '/imaging/sessions/', {
        query: { page: 1, nrows: 1, start_time: obsStart.value + 'Z', end_time: obsEnd.value + 'Z',
          source_name: watchSource.value.source, session_id: String(q.session), chan0: Number(q.band) }
      })
      if (found.data?.[0]) {
        if (q.from && q.to) pendingWindow = [String(q.from), String(q.to)]
        imgSession.value = found.data[0]
        await nextTick()
        // without the FRB timeline nothing picks a window, so apply it here
        if (pendingWindow && !isFrb.value) selectSpecgmWindow(...pendingWindow)
      }
    }
    if (q.tab != null) tabIndex.value = Math.max(0, Math.min(2, Number(q.tab) || 0))
  } catch {
    // a stale or broken address: start from the watch list
  } finally {
    await nextTick()
    restoring = false
  }
}
onMounted(restoreFromAddress)

watch([watchSource, imgSession, specgmQuery, tabIndex], () => {
  if (restoring) return
  const q: Record<string, string> = {}
  if (watchSource.value) {
    q.source = String(watchSource.value.id)
    if (imgSession.value) { q.session = String(imgSession.value.session_id); q.band = String(imgSession.value.chan0) }
    if (specgmQuery.value) { q.from = String(specgmQuery.value.start_time); q.to = String(specgmQuery.value.end_time) }
    q.tab = String(tabIndex.value)
  }
  router.replace({ query: q })
})

const crumbs = computed(() => {
  const out: { label: string, tab: number }[] = []
  if (!watchSource.value) return out
  out.push({ label: watchSource.value.source, tab: 0 })
  const s = imgSession.value
  if (s) out.push({ label: `${(s.chan0 * CHAN_BW_HZ / 1e6).toFixed(2)} MHz, ${tz.dateTime(s.start_time)} ${tz.zoneName(s.start_time)}`, tab: 1 })
  const q = specgmQuery.value
  if (s && q) out.push({ label: `${tz.clock(String(q.start_time))} to ${tz.clock(String(q.end_time))}`, tab: 2 })
  return out
})

useSeoMeta({
  title: 'Spectrograms @ LWA-Sevilleta',
  ogTitle:  'Spectrograms @ LWA-Sevilleta',
  description: 'View and download 80 ms, 25 kHz spectrograms of radio sources imaged by EPIC at the Long Wavelength Array station in Sevilleta, New Mexico.',
  ogDescription: 'View and download 80 ms, 25 kHz spectrograms of radio sources imaged by EPIC at the Long Wavelength Array station in Sevilleta, New Mexico.'
})
</script>
<template>

  <PageToolbar>
      <nav v-if="crumbs.length" aria-label="Current selection" class="flex flex-wrap items-center gap-1 min-w-0 text-sm">
        <template v-for="(c, i) in crumbs" :key="i">
          <UIcon v-if="i" name="i-heroicons-chevron-right-20-solid" class="w-4 h-4 text-gray-400 shrink-0" />
          <UButton size="xs" :color="i == crumbs.length - 1 ? 'primary' : 'gray'" variant="ghost" :label="c.label"
            class="truncate" @click="tabIndex = c.tab" />
        </template>
      </nav>
      <span v-else class="text-sm text-gray-500 dark:text-gray-400">Select a source to begin</span>
    <template #right><TimeZoneToggle /></template>
  </PageToolbar>
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
      <template #srcSelection>
        <SpectrogramWatchList v-model="watchSource" :day="listDay" class="mt-2" @picked="tabIndex = 1">
          <template #toolbar>
            <SpectrogramDayPicker v-model="listDay" :marks="frbDays" class="ml-2" @range="(a, b) => markRange = [a, b]">
              <template #legend>
                <span class="flex items-center gap-1.5"><span class="h-1.5 w-1.5 rounded-full bg-amber-500 dark:bg-amber-400" />CHIME/FRB event</span>
              </template>
            </SpectrogramDayPicker>
          </template>
        </SpectrogramWatchList>
      </template>

      <template #sessionSelection>
        <div v-if="watchSource" class="mt-2">
          <SpectrogramSessionList :session-query="sessionQuery" v-model="imgSession" @picked="tabIndex = 2" :frb="isFrb ? frb : null"
            :watch-window="isFrb ? watchWindow : null">
            <!-- FRB watches last hours, so their sessions are always listed in full -->
            <template v-if="!isFrb" #toolbar>
              <SpectrogramDayPicker v-model="sessionDay" :min="watchFirstDay" :max="watchLastDay" class="ml-2" />
            </template>
          </SpectrogramSessionList>
        </div>
        <div v-else="watchSource">
          <UCard>
            <UPageHero title="Select a source in the Source tab to list its sessions" />
          </UCard>

        </div>
      </template>

      <template #visualization>
        <div v-if="imgSession" class="mt-2">
          <UCard v-if="!isFrb" :ui="{ body: { padding: 'px-2 py-2 sm:p-2 m-2' } }">
            <div class="flex flex-wrap justify-evenly items-center">

              <div class="flex flex-wrap justify-center items-center gap-2  sm:flex-rows-3">
                <span class="text-md">Start time ({{ tz.zoneName(specgmStart || undefined) }})</span>
                <UInput type="datetime-local" v-model="specgmStartInput" step=1 :min="tz.toInput(selectedSessionStart)" :max="tz.toInput(selectedSessionEnd)"></UInput>
              </div>

              <div class="flex flex-wrap justify-center items-center gap-2">
                <span class="text-md">End time ({{ tz.zoneName(specgmEnd || undefined) }})</span>
                <UInput type="datetime-local" v-model="specgmEndInput" step=1 :min="tz.toInput(selectedSessionStart)" :max="tz.toInput(selectedSessionEnd)"></UInput>
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
          <SpectrogramFrbTimeline v-if="isFrb" class="m-2"
            :watch-source="watchSource" :img-session="imgSession" :window-start="specgmStart" :window-end="specgmEnd"
            @select="selectSpecgmWindow" @clear="clearSpecgmWindow" />
          <SpectrogramDisplay v-if="specgmQuery" :specgm-query="specgmQuery" :frb="frb"></SpectrogramDisplay>
        </div>
        <div v-else="imgSession">


          <UPageHero title="Select a session in the Session tab to explore its spectrograms" />

        </div>
      </template>
    </UTabs>
  </UDashboardPanelContent>
</template>
