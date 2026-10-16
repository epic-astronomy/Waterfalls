<script setup lang="ts">
import { format } from 'date-fns';
import type { DailyDigestSrc, DailyDigestSrcConfig, DailyDigestData, DailyDigestResp, DailyDigestTraceData } from '~/types';
import * as digestUtils from '~/lib/dailydigest'
import { CHAN_BW_HZ } from '~/lib/ndp'
import { v4 as uuidv4 } from "uuid"
import Plotly from 'plotly.js-dist-min'


const toast = useToast()
const colorMode = useColorMode()


const rtConfig = useRuntimeConfig()

const digestDay = ref<string | null>(null)
// days with a digest, for the dots on the calendar, fetched for the days in view
const digestRange = ref<[string, string] | null>(null)
const { data: digestDays } = await useLazyAsyncData<string[]>('digest-days', () => digestRange.value
  ? $fetch(rtConfig.public.fastapiBase + '/imaging/dailyobs/days/', { query: { start: digestRange.value[0], end: digestRange.value[1] } })
  : Promise.resolve([]), { watch: [digestRange], default: () => [], server: false })
const digestMarks = computed(() => Object.fromEntries((digestDays.value ?? []).map(d => [d, 1])))
const selectedSrc = ref('')
const chan_bw_hz = ref(2 * CHAN_BW_HZ)
const obsEnd = format((new Date().toISOString().slice(0, -1)), 'yyyy-MM-dd') // would be the current day in UTC
const selectedSrcConfigs = ref<{ [source: string]: number[] }>({}) // stores the observed frequencies for each source
const sourceNames = ref<String[]>([])


//////////////////////////////////
//Begin:  Source fetching based on date
//////////////////////////////////
const { pending, data: digestSrcs, error: error } = await useLazyAsyncData<DailyDigestSrc[]>(
  'dailysrcfetch',
  () => digestDay.value ? $fetch(rtConfig.public.fastapiBase + '/imaging/dailyobs/',
    {
      query: {
        day: digestDay.value
      }
    }) : Promise.resolve([])
  , {
    watch: [digestDay],
    default: () => []
  }
)

watch(() => error, (n, _) => {
  if (n.value) {
    toast.add({ title: 'Unable to fetch sources for the selected date.', color: 'red' })
  }
})


//digestDay.value = format((new Date().toISOString().slice(0, -1)),'yyyy-MM-dd')

// update the sources and their observed frequencies after selecting a date
watch(() => digestSrcs.value, (n, o) => {
  if (!n) return
  sourceNames.value = []
  selectedSrc.value = ''
  let configs: { [source: string]: number[] } = {}
  let cur_srcs: Set<String> = new Set()
  for (const obs of digestSrcs.value) {
    cur_srcs.add(obs.source_name)
    if (obs.source_name in configs) {
      configs[obs.source_name].push(obs.chan0)
    } else {
      configs[obs.source_name] = [obs.chan0]
    }
  }

  // assume a constant bandwidth for all observations
  for (const obs of digestSrcs.value) {
    chan_bw_hz.value = obs.chan_bw_hz
    break
  }
  selectedSrcConfigs.value = configs
  let sources: String[] = []
  for (const src of cur_srcs.values()) {
    sources.push(src)
  }
  sourceNames.value = sources
})
//////////////////////////////////
//End:  Source fetching based on date
//////////////////////////////////

//////////////////////////////////
//Start:  Data fetching
//////////////////////////////////
interface cfreqOpts {
  cfreq: number,
  label: string,
  chan0: number
}

const displayModes = [{
  label: '|I|',
  value: 'i'
}, {
  label: '|V|',
  value: 'v'
}]

const selectedMode = ref('i')

const fetchTrigger = ref('')
const selectedCfreq = ref<cfreqOpts>()
const { pending: pending2, data: digestData, error: dataError } = await useLazyAsyncData<DailyDigestResp>(
  'dailydatafetch',
  () => !fetchTrigger.value ? Promise.resolve(null) : $fetch(rtConfig.public.fastapiBase + '/imaging/dailydigest/',
    {
      query: {
        day: digestDay.value,
        source_name: selectedSrc.value,
        cfreq: selectedCfreq?.value?.cfreq
      }
    })
  , {
    watch: [() => fetchTrigger.value],
    default: () => null
  }
)


// const cfreqLabels = computed(() => {
//   if (selectedSrc.value == '' || !(selectedSrc.value in selectedSrcConfigs.value)) return []
//   selectedCfreq.value = undefined

//   let cfreqs: cfreqOpts[] = []
//   let nchan = 128 * 25000 / chan_bw_hz.value
//   for (const chan0 of selectedSrcConfigs.value[selectedSrc.value]) {
//     let cfreq_comp = (chan0 + nchan / 2 - 1) * 25000
//     let cfreq = chan0 * 0.025 + nchan * chan_bw_hz.value / 2 / 1e6
//     cfreqs.push({ 'cfreq': cfreq_comp, 'chan0': chan0, 'label': String((cfreq).toFixed(2)) + ' MHz' })
//   }

//   return cfreqs

// })

// const plotDataExists = computed(()=>{
//   return plotData.value.length !=0
// })

// var stokes_I = Array<Float32Array>()
// var stokes_V = Array<Float32Array>()
// var raw_data = Array<Float32Array>()
// var plotData = ref(Array<Float32Array>())
var plotTraces = ref<{ [cfreq: number]: DailyDigestTraceData }>({})
var plotDataRaw: DailyDigestResp
const plotlyDivId = `plotly-${uuidv4()}`
// at least 1: with auto-correlations removed Stokes can be negative, and a
// fractional power of a negative value leaves holes in the image
const gammaCorr = ref<number>(1)

const plotlyAxes = reactive({
  xLabels: Array<string>(),
  yLabels: ref(Array<number>())
})

// One panel per band, highest frequency at the top, stacked without gaps on
// a shared time axis. Each band has its own colour scale, because the sky
// brightness differs by an order of magnitude across the bands.
const PANEL_PX = 130
const ink = computed(() => colorMode.value == 'dark' ? 'white' : 'black')
const paper = computed(() => colorMode.value == 'dark' ? '#131826' : 'rgb(255,255,255)')
const bandKeys = computed(() => Object.keys(plotTraces.value).map(Number).sort((a, b) => b - a))
const plotHeight = computed(() => bandKeys.value.length * PANEL_PX + 110)
const utcStr = (ms: number) => new Date(ms).toISOString().slice(0, 23).replace('T', ' ')

// zoom window from the slider, in UTC ms; null for the whole day
const zoom = ref<[number, number] | null>(null)

const plotlyLayout = computed(() => {
  const n = bandKeys.value.length
  const font = { family: 'Courier New, monospace', color: ink.value }
  const layout: Record<string, any> = {
    title: { text: selectedSrc.value + ' | LWA-Sevilleta', font: { ...font, size: 22 } },
    height: plotHeight.value, margin: { l: 80, r: 90, t: 50, b: 55 },
    paper_bgcolor: paper.value, plot_bgcolor: paper.value, font, hovermode: 'closest', showlegend: false,
    annotations: [{ text: 'Frequency (MHz)', textangle: -90, xref: 'paper', yref: 'paper', x: 0, xshift: -70, y: 0.5,
      showarrow: false, font: { ...font, size: 16 } }]
  }
  bandKeys.value.forEach((_, i) => {
    const s = i == 0 ? '' : String(i + 1)
    const top = 1 - i / n, bottom = 1 - (i + 1) / n
    layout[`xaxis${s}`] = {
      anchor: `y${s}`, type: 'date', matches: i == 0 ? undefined : 'x', showticklabels: i == n - 1,
      title: i == n - 1 ? { text: 'Time (UTC)', font: { ...font, size: 16 } } : undefined,
      tickfont: font, tickcolor: ink.value, linecolor: ink.value, showline: true, mirror: true, ticks: 'outside',
      range: zoom.value ? zoom.value.map(utcStr) : undefined
    }
    layout[`yaxis${s}`] = {
      anchor: `x${s}`, domain: [bottom, top], tickfont: font, tickcolor: ink.value, linecolor: ink.value,
      showline: true, mirror: true, ticks: 'outside', nticks: 4
    }
  })
  return layout
})

var plotlyConfig = computed(() => {
  return {
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'zoom2d', 'pan2d', ' zoomIn2d', 'zoomOut2d', 'autoScale2d', 'zoomIn'],
    toImageButtonOptions: {
      format: 'png', // one of png, svg, jpeg, webp
      filename: 'EPIC Daily Digest - ' + selectedSrc.value,
      scale: 3
    }, responsive: true, displaylogo: false
  }
})

// colour limits of a band from its 1st and 99th percentiles, so a few bright
// or negative outliers do not flatten the rest
function robustLimits(z: Float32Array[]) {
  const v: number[] = []
  for (const row of z) for (let j = 0; j < row.length; j += Math.max(1, Math.floor(row.length / 400))) if (isFinite(row[j])) v.push(row[j])
  if (!v.length) return {}
  v.sort((a, b) => a - b)
  return { zmin: v[Math.floor(0.01 * (v.length - 1))], zmax: v[Math.ceil(0.99 * (v.length - 1))] }
}

var plotlyTraces = computed(() => {
  const n = bandKeys.value.length
  return bandKeys.value.map((cfreq, i) => {
    const trace = plotTraces.value[cfreq]
    const s = i == 0 ? '' : String(i + 1)
    const z = selectedMode.value == 'i' ? trace.stokes_I : trace.stokes_V
    return {
      ...robustLimits(z),
      name: (cfreq / 1e6).toFixed(2) + ' MHz',
      z, type: 'heatmap',
      x: trace.img_time, y: trace.freqs, xaxis: `x${s}`, yaxis: `y${s}`,
      hoverongaps: false, colorscale: 'Viridis', zsmooth: 'best',
      hovertemplate: '%{x|%H:%M:%S} UTC<br>%{y:.2f} MHz<br>%{z:.3g}<extra></extra>',
      colorbar: {
        y: 1 - (i + 0.5) / n, len: 1 / n, thickness: 12, x: 1.01, xpad: 4, exponentformat: 'e', nticks: 4,
        outlinecolor: ink.value, tickcolor: ink.value, tickfont: { color: ink.value, family: 'Courier New, monospace', size: 10 },
        title: i == 0 ? { text: selectedMode.value == 'i' ? '|I|' : '|V|', font: { color: ink.value, size: 12 } } : undefined
      }
    }
  })
})

// Light curve behind the zoom slider: Stokes I summed over the channels of
// each band, each band divided by its median so none dominates, averaged
// across the bands in bins of the digest cadence
const lightCurve = computed(() => {
  const keys = bandKeys.value
  if (!keys.length) return { start: 0, end: 1, times: [] as number[], values: [] as number[] }
  const ms = (t: string) => Date.parse(t.replace(' ', 'T').replace(/Z?$/, 'Z'))
  const all = keys.flatMap(k => plotTraces.value[k].img_time.map(ms))
  const lo = Math.min(...all), hi = Math.max(...all)
  const first = plotTraces.value[keys[0]].img_time.map(ms)
  const steps = first.slice(1).map((t, j) => t - first[j]).filter(d => d > 0).sort((a, b) => a - b)
  const w = Math.max(1, steps[Math.floor(steps.length / 2)] ?? (hi - lo) / 300)
  const nBins = Math.max(1, Math.min(2000, Math.ceil((hi - lo) / w)))
  const sum = new Float64Array(nBins), cnt = new Float64Array(nBins)
  for (const k of keys) {
    const tr = plotTraces.value[k]
    const tot = tr.img_time.map((_, j) => tr.stokes_I.reduce((a, ch) => a + (isFinite(ch[j]) ? ch[j] : 0), 0))
    const sorted = [...tot].sort((a, b) => a - b)
    const med = Math.abs(sorted[Math.floor(sorted.length / 2)]) || 1
    tr.img_time.forEach((t, j) => {
      const b = Math.min(nBins - 1, Math.floor((ms(t) - lo) / w))
      sum[b] += tot[j] / med; cnt[b]++
    })
  }
  return {
    start: lo, end: hi,
    times: Array.from({ length: nBins }, (_, b) => lo + (b + 0.5) * w),
    values: Array.from(sum, (v, b) => cnt[b] ? v / cnt[b] : NaN)
  }
})

function updatePlot() {
  if (fetchDataDisabled.value || !bandKeys.value.length) return
  const el = document.getElementById(plotlyDivId)
  if (!el || !el.clientWidth) return
  Plotly.react(el, plotlyTraces.value, plotlyLayout.value, plotlyConfig.value).then(() => {
    // a double click on the plot resets the zoom
    ;(el as any).removeAllListeners?.('plotly_relayout')
    ;(el as any).on?.('plotly_relayout', (e: Record<string, any>) => { if (e['xaxis.autorange']) zoom.value = null })
  })
}
watch(zoom, () => updatePlot())

// function updatePlotData() {
//   switch (selectedMode.value) {
//     case 'i':
//       plotData.value = stokes_I
//       break
//     case 'v':
//       plotData.value = stokes_V
//       break
//   }
// }

watch(() => selectedMode.value, (newMode, _) => {
  // updatePlotData()
  updatePlot()
})

watch(() => gammaCorr.value, (n, _) => {
  plotTraces.value = digestUtils.split_data_freq(plotDataRaw, n)
  updatePlot()
})

watch(() => digestData.value, (newData, _) => {
  if (!newData) return
  plotDataRaw = newData
  plotTraces.value = digestUtils.split_data_freq(plotDataRaw, gammaCorr.value)
  zoom.value = null
  nextTick(updatePlot)
})

watch(() => dataError, (n, _) => {
  if (n.value) {
    toast.add({ title: 'Unable to fetch sources for the selected date.', color: 'red' })
  }
})

watch(() => colorMode.value, (n, o) => {
  updatePlot()
})

function displayData() {
  if (selectedSrc.value != '') {
    fetchTrigger.value = selectedSrc.value + digestDay.value
  }
}

const fetchDataDisabled = computed(() => {
  return selectedSrc.value == '' ? true : false
})

const resizeConfig = {
  resizeObserver: {} as ResizeObserver,
  timeOutFunctionId: {} as NodeJS.Timeout
}

const setResizeObserver = () => {
  resizeConfig.resizeObserver = new ResizeObserver(() => {
    // debounce the reset
    clearTimeout(resizeConfig.timeOutFunctionId);
    resizeConfig.timeOutFunctionId = setTimeout(() => {
      updatePlot();
    }, 100);
  });
  const plotlyElm = document.getElementById(plotlyDivId);
  if (plotlyElm) {
    resizeConfig.resizeObserver.observe(plotlyElm);
  }
}
onMounted(() => {
  setResizeObserver()
})

onBeforeUnmount(() => {
  resizeConfig.resizeObserver.disconnect();
});

</script>
<template>
  <UDashboardNavbar title="Daily Digest - Long Wavelength Array, Sevilleta"></UDashboardNavbar>
  <UDashboardPanelContent>
    <UCard :ui="{ body: { padding: 'px-2 py-2 sm:p-2 m-2' } }" class="relative">
      <UProgress v-if="pending || pending2" animation="elastic" size="xs" class="p-0 m-0 top-0 left-0 absolute" />

      <div class="flex flex-wrap justify-evenly items-center">


        <div class="flex flex-wrap justify-center items-center gap-2">
          <span class="text-md">Day (UTC)</span>
          <SpectrogramDayPicker v-model="digestDay" :marks="digestMarks" min="2024-10-16" :max="obsEnd" utc placeholder="Select a day"
            :clearable="false" @range="(a, b) => digestRange = [a < '2024-10-16' ? '2024-10-16' : a, b > obsEnd ? obsEnd : b]">
            <template #legend>
              <span class="flex items-center gap-1.5"><span class="h-1.5 w-1.5 rounded-full bg-amber-500 dark:bg-amber-400" />Digest available</span>
            </template>
          </SpectrogramDayPicker>
        </div>
        <div class="flex flex-wrap justify-center items-center gap-2">
          <span class="text-md">Source</span>
          <USelect v-model="selectedSrc" :options="sourceNames" placeholder="Select a source">
          </USelect>
        </div>
        <div class="flex justify-center space-x-4 items-center">
          <div>Stokes</div>
          <div style="font-family: monospace;" class="flex justify-center space-x-4 items-center">
            <URadio v-for="mode of displayModes" :key="mode.value" v-model="selectedMode" v-bind="mode" legend="Show" />
          </div>
        </div>
        <div class="flex flex-wrap justify-center items-center gap-2 xs">
          <span class="text-md">Scale exponent</span>
          <UInput v-model="gammaCorr" type="number" step="0.1" min="1" max="20" />
        </div>
        <UButton :ui="{ rounded: 'rounded-md' }" variant="outline" label="Display" @click="displayData"
          :disabled="fetchDataDisabled">
        </UButton>
      </div>
    </UCard>
    <!-- always in the page, so the resize observer can watch it -->
    <UCard v-show="bandKeys.length" class="mt-2" :ui="{ body: { padding: 'px-1 py-1 sm:p-2' } }">
      <div :id="plotlyDivId" :style="{ height: `${plotHeight}px` }"></div>
      <div v-if="lightCurve.times.length" class="px-2 pb-1 sm:pl-[80px] sm:pr-[90px]">
        <div class="mb-1 text-xs text-gray-500 dark:text-gray-400">Drag the handles or the window to zoom in time. The line is Stokes I summed over the channels and averaged over the bands.</div>
        <SpectrogramTimeRangeSlider v-model="zoom" :times="lightCurve.times" :values="lightCurve.values"
          :start="lightCurve.start" :end="lightCurve.end" />
      </div>
    </UCard>
    <UCard v-if="!bandKeys.length" class="mt-2">
      <UPageHero title="Select a day and a source to continue" align="center" />
    </UCard>
  </UDashboardPanelContent>
</template>