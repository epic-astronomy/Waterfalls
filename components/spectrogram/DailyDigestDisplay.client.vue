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

const displayModes = [{ label: 'Stokes I', value: 'i' }, { label: 'Stokes V', value: 'v' }]

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
// The exponent stretches the colour map, not the data: a value u in [0, 1]
// of the colour range gets the colour Viridis(u^exponent), so negative values
// need no special care. The slider is logarithmic, from 1/4 to 16, and
// starts at 4.
//
// To keep the slider responsive, each band is drawn as an image rather than
// a Plotly heatmap. When the data arrive, every pixel is reduced once to an
// 8-bit index into the colour range, on a regular time grid. Moving the
// slider then only rebuilds a 256-colour palette, recolours these small
// images and swaps them into the plot, which Plotly does without redrawing
// the axes. Invisible heatmaps underneath keep the hover readout.
const STRETCH_DEFAULT = 100
const stretchPos = ref(STRETCH_DEFAULT) // -100 to 200
const exponent = computed(() => Math.pow(4, stretchPos.value / 100))
const VIRIDIS = ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
  .map(h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)))
function viridis(t: number) {
  const x = Math.min(1, Math.max(0, t)) * (VIRIDIS.length - 1)
  const i = Math.min(VIRIDIS.length - 2, Math.floor(x)), f = x - i
  const c = VIRIDIS[i].map((v, k) => Math.round(v + f * (VIRIDIS[i + 1][k] - v)))
  return `rgb(${c.join(',')})`
}
const palette = (g: number) => Array.from({ length: 256 }, (_, k) => viridis(Math.pow(k / 255, g))
  .slice(4, -1).split(',').map(Number))
const gradient = computed(() => `linear-gradient(to top, ${Array.from({ length: 17 }, (_, k) =>
  `${viridis(Math.pow(k / 16, exponent.value))} ${(100 * k / 16).toFixed(1)}%`).join(', ')})`)

const plotlyAxes = reactive({
  xLabels: Array<string>(),
  yLabels: ref(Array<number>())
})

// One panel per band, highest frequency at the top, stacked without gaps on
// a shared time axis. Each band has its own colour scale, because the sky
// brightness differs by an order of magnitude across the bands.
// Panels are sized so the whole digest fits the window below the plot's top
// edge, between 60 and 130 px per band; unchecking Fit to window gives every
// band 130 px
const PANEL_PX = 130
const PANEL_MIN_PX = 60
const PLOT_MARGIN_PX = 75 // the top and bottom margins of the plot
const fitWindow = ref(true)
const windowHeight = ref(import.meta.client ? window.innerHeight : 900)
const plotTop = ref(300)
const plotBox = ref<HTMLElement>()
function measure() {
  windowHeight.value = window.innerHeight
  if (plotBox.value) plotTop.value = plotBox.value.getBoundingClientRect().top + (plotBox.value.closest('.overflow-y-auto')?.scrollTop ?? 0)
}
// the title and slider above the plot settle after the data arrive
const headerBox = ref<HTMLElement>()
const headerObserver = import.meta.client ? new ResizeObserver(() => measure()) : null
watch(headerBox, (el, old) => { if (old) headerObserver?.unobserve(old); if (el) headerObserver?.observe(el) })
onMounted(() => window.addEventListener('resize', measure))
onBeforeUnmount(() => { window.removeEventListener('resize', measure); headerObserver?.disconnect() })
const panelPx = computed(() => {
  const n = bandKeys.value.length || 1
  if (!fitWindow.value) return PANEL_PX
  return Math.max(PANEL_MIN_PX, Math.min(PANEL_PX, Math.floor((windowHeight.value - plotTop.value - 16 - PLOT_MARGIN_PX) / n)))
})
const ink = computed(() => colorMode.value == 'dark' ? 'white' : 'black')
const paper = computed(() => colorMode.value == 'dark' ? '#131826' : 'rgb(255,255,255)')
const bandKeys = computed(() => Object.keys(plotTraces.value).map(Number).sort((a, b) => b - a))
const plotHeight = computed(() => bandKeys.value.length * panelPx.value + PLOT_MARGIN_PX)
watch(plotHeight, () => nextTick(updatePlot))
const utcStr = (ms: number) => new Date(ms).toISOString().slice(0, 23).replace('T', ' ')

// zoom window from the slider, in UTC ms; null for the whole day
const zoom = ref<[number, number] | null>(null)

const plotlyLayout = computed(() => {
  const n = bandKeys.value.length
  const font = { family: 'Courier New, monospace', color: ink.value }
  const layout: Record<string, any> = {
    height: plotHeight.value, margin: { l: 80, r: 110, t: 20, b: 55 },
    paper_bgcolor: paper.value, plot_bgcolor: 'rgba(0,0,0,0)', font, hovermode: 'closest', showlegend: false,
    images: bandImages(exponent.value),
    annotations: [{ text: 'Frequency (MHz)', textangle: -90, xref: 'paper', yref: 'paper', x: 0, xshift: -70, y: 0.5,
      showarrow: false, font: { ...font, size: 16 } }]
  }
  bandKeys.value.forEach((_, i) => {
    const s = i == 0 ? '' : String(i + 1)
    const top = 1 - i / n, bottom = 1 - (i + 1) / n
    layout[`xaxis${s}`] = {
      anchor: `y${s}`, type: 'date', matches: i == 0 ? undefined : 'x', showticklabels: i == n - 1,
      title: i == n - 1 ? { text: 'Time (UTC)', font: { ...font, size: 16 } } : undefined,
      tickfont: font, tickcolor: ink.value, linecolor: ink.value, showline: true, mirror: true, ticks: 'outside', showgrid: false,
      range: zoom.value ? zoom.value.map(utcStr) : undefined
    }
    layout[`yaxis${s}`] = {
      anchor: `x${s}`, domain: [bottom, top], tickfont: font, tickcolor: ink.value, linecolor: ink.value,
      showline: true, mirror: true, ticks: 'outside', nticks: 4, showgrid: false, zeroline: false
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

// Every channel is expressed as its departure from its median over the day,
// in units of its robust scatter (1.4826 times the median absolute
// deviation). This removes the bandpass and the brightness differences
// between bands, so all panels share one colour scale.
function normalise(rows: Float32Array[], blank: Uint8Array) {
  return rows.map(row => {
    const v = Array.from(row).filter((x, j) => isFinite(x) && !blank[j]).sort((a, b) => a - b)
    if (!v.length) return row.map(() => NaN)
    const med = v[Math.floor(v.length / 2)]
    const dev = v.map(x => Math.abs(x - med)).sort((a, b) => a - b)
    const sig = 1.4826 * dev[Math.floor(dev.length / 2)] || 1
    return row.map((x, j) => blank[j] ? NaN : (x - med) / sig)
  })
}

// Samples where a band's output went dead: the mean of |Stokes I| over the
// channels falls below 1% of the band's typical (90th percentile) level.
// With the auto-correlations removed the plain mean of a healthy low band
// can sit near zero, so the magnitude is tested. From 13:14 to 14:15 UTC on
// 2026-10-15 every band dropped by a factor of 100 to 10^8. Blank samples
// are shown as gaps and left out of the statistics and the light curve.
const meanI = (tr: DailyDigestTraceData, j: number) => {
  let sum = 0, n = 0
  for (const ch of tr.stokes_I) if (isFinite(ch[j])) { sum += ch[j]; n++ }
  return n >= tr.stokes_I.length / 2 ? sum / n : NaN
}
const blanks = computed(() => Object.fromEntries(bandKeys.value.map(k => {
  const tr = plotTraces.value[k]
  const level = tr.img_time.map((_, j) => {
    let sum = 0, n = 0
    for (const ch of tr.stokes_I) if (isFinite(ch[j])) { sum += Math.abs(ch[j]); n++ }
    return n >= tr.stokes_I.length / 2 ? sum / n : NaN
  })
  const ok = level.filter(isFinite).sort((a, b) => a - b)
  const typical = ok[Math.floor(0.9 * (ok.length - 1))] ?? 0
  return [k, Uint8Array.from(level, v => !isFinite(v) || v < 1e-2 * typical ? 1 : 0)]
})))
const normalised = computed(() => Object.fromEntries(bandKeys.value.map(k => [k, {
  i: normalise(plotTraces.value[k].stokes_I, blanks.value[k]), v: normalise(plotTraces.value[k].stokes_V, blanks.value[k])
}])))
// the shared colour range, from the 1st and 99th percentiles of all panels,
const colourRange = computed(() => {
  const v: number[] = []
  for (const k of bandKeys.value) for (const row of normalised.value[k][selectedMode.value as 'i' | 'v'])
    for (let j = 0; j < row.length; j += Math.max(1, Math.floor(row.length / 200))) if (isFinite(row[j])) v.push(row[j])
  if (!v.length) return [-3, 5]
  v.sort((a, b) => a - b)
  // at most 10 sigma either side, so a transient such as a band restarting
  // does not compress the rest of the day into a few colours
  return [Math.max(-10, v[Math.floor(0.01 * (v.length - 1))]), Math.min(10, v[Math.ceil(0.99 * (v.length - 1))])]
})

// Each band on a regular time grid at the digest cadence, as colour indices
// (0 to 254) across the shared colour range; 255 marks no data
const ms = (t: string) => Date.parse(t.replace(' ', 'T').replace(/Z?$/, 'Z'))
const indexed = computed(() => {
  const [lo, hi] = colourRange.value
  return bandKeys.value.map((k, i) => {
    const tr = plotTraces.value[k]
    const times = tr.img_time.map(ms)
    const steps = times.slice(1).map((t, j) => t - times[j]).filter(d => d > 0).sort((a, b) => a - b)
    const dt = steps[Math.floor(steps.length / 2)] || 60e3
    const nT = Math.max(1, Math.round((times[times.length - 1] - times[0]) / dt) + 1)
    const z = normalised.value[k][selectedMode.value as 'i' | 'v']
    const nF = z.length
    const idx = new Uint8Array(nT * nF).fill(255)
    times.forEach((t, j) => {
      const col = Math.min(nT - 1, Math.round((t - times[0]) / dt))
      for (let c = 0; c < nF; c++) {
        const v = z[c][j]
        // rows from the top, highest frequency first
        if (isFinite(v)) idx[(nF - 1 - c) * nT + col] = Math.round(254 * Math.min(1, Math.max(0, (v - lo) / (hi - lo))))
      }
    })
    const df = tr.freqs.length > 1 ? tr.freqs[1] - tr.freqs[0] : 0.05
    return { s: i == 0 ? '' : String(i + 1), idx, nT, nF, x0: times[0] - dt / 2, width: nT * dt, top: tr.freqs[nF - 1] + df / 2, height: nF * df }
  })
})

// the images for one exponent, as Plotly layout images
const canvas = import.meta.client ? document.createElement('canvas') : null
function bandImages(g: number) {
  if (!canvas) return []
  const pal = palette(g)
  return indexed.value.map(b => {
    canvas.width = b.nT; canvas.height = b.nF
    const ctx = canvas.getContext('2d')!
    const img = ctx.createImageData(b.nT, b.nF)
    for (let p = 0; p < b.idx.length; p++) {
      const k = b.idx[p]
      if (k == 255) continue
      const c = pal[k]
      img.data[4 * p] = c[0]; img.data[4 * p + 1] = c[1]; img.data[4 * p + 2] = c[2]; img.data[4 * p + 3] = 255
    }
    ctx.putImageData(img, 0, 0)
    return {
      source: canvas.toDataURL(), xref: `x${b.s}`, yref: `y${b.s}`, x: utcStr(b.x0), y: b.top, sizex: b.width, sizey: b.height,
      xanchor: 'left', yanchor: 'top', sizing: 'stretch', layer: 'below'
    }
  })
}
const colourTicks = computed(() => {
  const [lo, hi] = colourRange.value
  const step = [0.5, 1, 2, 5, 10, 20].find(st => (hi - lo) / st <= 6) ?? 50
  const out = []
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push({ v, pos: 100 * (v - lo) / (hi - lo) })
  return out
})

var plotlyTraces = computed(() => {
  const n = bandKeys.value.length
  return bandKeys.value.map((cfreq, i) => {
    const trace = plotTraces.value[cfreq]
    const s = i == 0 ? '' : String(i + 1)
    const z = normalised.value[cfreq][selectedMode.value as 'i' | 'v']
    return {
      name: (cfreq / 1e6).toFixed(2) + ' MHz',
      z, type: 'heatmap',
      x: trace.img_time, y: trace.freqs, xaxis: `x${s}`, yaxis: `y${s}`,
      hoverongaps: false, opacity: 0, showscale: false, zsmooth: false,
      hovertemplate: '%{x|%H:%M:%S} UTC<br>%{y:.2f} MHz<br>%{z:.1f} σ<extra></extra>'
    }
  })
})

// Activity curve behind the zoom slider: at each time, the root mean square
// over every channel of every band of the normalised values the panels show
// (Stokes I or V as selected), in bins of the digest cadence. It is low when
// the spectrum is as usual and peaks at bursts, interference and other
// changes, wherever in the band they occur. A median or mean over the bands
// mostly followed slow drifts and hid events confined to a few channels.
const lightCurve = computed(() => {
  const keys = bandKeys.value
  if (!keys.length) return { start: 0, end: 1, times: [] as number[], values: [] as number[] }
  const all = keys.flatMap(k => plotTraces.value[k].img_time.map(ms))
  const lo = Math.min(...all), hi = Math.max(...all)
  const first = plotTraces.value[keys[0]].img_time.map(ms)
  const steps = first.slice(1).map((t, j) => t - first[j]).filter(d => d > 0).sort((a, b) => a - b)
  const w = Math.max(1, steps[Math.floor(steps.length / 2)] ?? (hi - lo) / 300)
  const nBins = Math.max(1, Math.min(2000, Math.ceil((hi - lo) / w)))
  const sumSq = new Float64Array(nBins), cnt = new Float64Array(nBins)
  for (const k of keys) {
    const z = normalised.value[k][selectedMode.value as 'i' | 'v']
    plotTraces.value[k].img_time.forEach((t, j) => {
      const b = Math.min(nBins - 1, Math.floor((ms(t) - lo) / w))
      for (const row of z) if (isFinite(row[j])) { sumSq[b] += row[j] * row[j]; cnt[b]++ }
    })
  }
  return {
    start: lo, end: hi,
    times: Array.from({ length: nBins }, (_, b) => lo + (b + 0.5) * w),
    // on a log scale, so the peaks keep their shape and the quiet baseline shows
    values: Array.from(sumSq, (v, b) => cnt[b] && v > 0 ? 0.5 * Math.log10(v / cnt[b]) : NaN)
  }
})

function updatePlot() {
  if (fetchDataDisabled.value || !bandKeys.value.length) return
  // the title and slider above may have just appeared; a new height redraws
  measure()
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

// the slider only recolours the images, at most once per frame
let stretchFrame = 0
watch(exponent, g => {
  cancelAnimationFrame(stretchFrame)
  stretchFrame = requestAnimationFrame(() => {
    const el = document.getElementById(plotlyDivId) as any
    if (el?.data) Plotly.relayout(el, { images: bandImages(g) })
  })
})

watch(() => digestData.value, (newData, _) => {
  if (!newData) return
  plotDataRaw = newData
  plotTraces.value = digestUtils.split_data_freq(plotDataRaw)
  zoom.value = null
  nextTick(() => { measure(); updatePlot() })
})

watch(() => dataError, (n, _) => {
  if (n.value) {
    toast.add({ title: 'Unable to fetch sources for the selected date.', color: 'red' })
  }
})

watch(() => colorMode.value, (n, o) => {
  updatePlot()
})

// a day and a source are all that is needed
watch([selectedSrc, digestDay], ([src, day]) => {
  if (src && day) fetchTrigger.value = `${src}|${day}`
})

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
  <!-- the page's controls sit in the header bar -->
  <PageToolbar>
      <UProgress v-if="pending || pending2" animation="elastic" size="xs" class="p-0 m-0 top-0 left-0 absolute" />


        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-600 dark:text-gray-300">Day (UTC)</span>
          <SpectrogramDayPicker v-model="digestDay" :marks="digestMarks" min="2024-10-16" :max="obsEnd" utc placeholder="Select a day"
            :clearable="false" @range="(a, b) => digestRange = [a < '2024-10-16' ? '2024-10-16' : a, b > obsEnd ? obsEnd : b]">
            <template #legend>
              <span class="flex items-center gap-1.5"><span class="h-1.5 w-1.5 rounded-full bg-amber-500 dark:bg-amber-400" />Digest available</span>
            </template>
          </SpectrogramDayPicker>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-600 dark:text-gray-300">Source</span>
          <USelect v-model="selectedSrc" :options="sourceNames" placeholder="Select a source">
          </USelect>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-600 dark:text-gray-300">Stokes</span>
          <USelect v-model="selectedMode" :options="displayModes" option-attribute="label" value-attribute="value" />
        </div>
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-600 dark:text-gray-300">Colour exponent</span>
          <URange v-model="stretchPos" :min="-100" :max="200" :step="1" size="sm" class="w-40" aria-label="Colour exponent" />
          <span class="w-10 text-sm tabular-nums">{{ exponent.toFixed(2) }}</span>
          <UButton v-if="stretchPos != STRETCH_DEFAULT" size="2xs" color="gray" variant="ghost" icon="i-heroicons-arrow-uturn-left"
            aria-label="Reset the colour exponent" @click="stretchPos = STRETCH_DEFAULT" />
        </div>
  </PageToolbar>
  <UDashboardPanelContent>
    <!-- always in the page, so the resize observer can watch it -->
    <UCard v-show="bandKeys.length" :ui="{ body: { padding: 'px-1 py-1 sm:p-2' } }">
      <div ref="headerBox">
      <div class="flex flex-wrap items-center justify-between gap-2 px-2 sm:pl-[80px] sm:pr-[110px]">
        <h2 class="font-mono text-lg">{{ selectedSrc }} | LWA-Sevilleta | {{ digestDay }}</h2>
        <UCheckbox v-model="fitWindow" label="Fit to window" />
      </div>
      <div v-if="lightCurve.times.length" class="px-2 pt-1 sm:pl-[80px] sm:pr-[110px]">
        <SpectrogramTimeRangeSlider v-model="zoom" :times="lightCurve.times" :values="lightCurve.values"
          :start="lightCurve.start" :end="lightCurve.end" />
      </div>
      </div>
      <div ref="plotBox" class="relative">
        <div :id="plotlyDivId" :style="{ height: `${plotHeight}px` }"></div>
        <!-- the colour bar, outside Plotly so the exponent slider does not redraw the plot -->
        <div v-if="bandKeys.length" class="absolute right-0 flex pointer-events-none" :style="{ top: '20px', bottom: '55px', width: '104px' }">
          <div class="relative ml-2 w-3.5 ring-1 ring-gray-900 dark:ring-white" :style="{ background: gradient }">
            <div v-for="t in colourTicks" :key="t.v" class="absolute left-full flex items-center -translate-y-1/2" :style="{ bottom: `calc(${t.pos}% - 0.5px)`, transform: 'translateY(50%)' }">
              <span class="w-1 h-px bg-gray-900 dark:bg-white" />
              <span class="ml-1 text-[11px] font-mono text-gray-900 dark:text-white">{{ t.v }}</span>
            </div>
          </div>
          <div class="ml-7 flex items-center">
            <span class="whitespace-nowrap text-xs text-gray-900 dark:text-white [writing-mode:vertical-rl]">Stokes {{ selectedMode.toUpperCase() }}, σ from channel median</span>
          </div>
        </div>
      </div>
    </UCard>
    <UCard v-if="!bandKeys.length">
      <UPageHero title="Select a day and a source to continue" align="center" />
    </UCard>
  </UDashboardPanelContent>
</template>