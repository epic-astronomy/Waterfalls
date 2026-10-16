<script setup lang="ts">
import type { PropType } from 'vue';
import type { SpecgmData, SpecgmQuery } from '~/types'
import * as specUtils from '~/lib/spectrogram'
import { CHAN_BW_HZ } from '~/lib/ndp'
import { freqAtMs, utcMs, type FrbParams } from '~/lib/frb'
const tz = useTimeZone()
import Plotly from 'plotly.js-dist-min'
import { v4 as uuidv4 } from "uuid"

const toast = useToast()
const colorMode = useColorMode()


const rtConfig = useRuntimeConfig()
const props = defineProps<{
  specgmQuery: SpecgmQuery,
  frb?: FrbParams | null
}>()
const showDispersion = ref(true)

// const startFreq = inject('startFreq')
// const nChans = inject('nChans')
// const chanBwHz = inject('chanBwHz')

const nChans = computed(() => props.specgmQuery.n_chan)
const startChan = computed(() => props.specgmQuery.start_chan)
const chanBwHz = computed(() => props.specgmQuery.chan_bw_hz)
const nPols = computed(() => props.specgmQuery.n_pols)
// const nBufElems = 128 * nPols
//const sourceName = 'PSR B1133+16'


// Automatic RFI flagging with the analysis flagger (lib/rfi.ts, the CHIME/FRB
// L1 chain), run in a worker once per window and mode and cached, so turning
// it on and off, or returning to a mode, costs nothing
const IMAGE_DT_S = 0.0836
// kept across windows and sessions, which rebuild this component
const rfiOn = useState('spectrogram-flag-rfi', () => true)
const rfiMasks = ref<Record<string, Uint8Array[]>>({})
const rfiPending = ref(false)
let rfiWorker: Worker | null = null
let rfiRequest = 0
let rfiRequestMode = ''
const rfiFlagged = computed(() => {
  const m = rfiMasks.value[selectedMode.value]
  if (!m) return null
  let bad = 0, n = 0
  for (const row of m) { n += row.length; for (let t = 0; t < row.length; t++) bad += 1 - row[t] }
  return n ? 100 * bad / n : 0
})
function requestRfiMask() {
  if (!rfiOn.value || !plotDataRaw.length || rfiMasks.value[selectedMode.value]) return
  if (!rfiWorker) {
    rfiWorker = new Worker(new URL('../../lib/rfi.worker.ts', import.meta.url), { type: 'module' })
    rfiWorker.onmessage = (e: MessageEvent<{ id: number, mask: Uint8Array[] }>) => {
      // a newer window or mode supersedes this one
      if (e.data.id != rfiRequest) return
      rfiMasks.value = { ...rfiMasks.value, [rfiRequestMode]: e.data.mask }
      rfiPending.value = false
      updatePlot()
    }
  }
  rfiRequest++
  rfiRequestMode = selectedMode.value
  rfiPending.value = true
  rfiWorker.postMessage({ id: rfiRequest, channels: plotDataRaw.map(r => r.slice()), dt: IMAGE_DT_S })
}
onBeforeUnmount(() => rfiWorker?.terminate())


var xx_data = Array<Float32Array>()
var plotDataRaw = Array<Float32Array>()
const plotData = ref(Array<Float32Array>())
var yy_data = Array<Float32Array>()
var stokes_I = Array<Float32Array>()
var raw_data = Array<Float32Array>()
const plotlyAxes = reactive({
  xLabels: Array<string>(),
  yLabels: ref(Array<number>())
})
const xLabels = ref(Array<string>())
const yLabels = ref(Array<number>())
const plotlyDivId = `plotly-${uuidv4()}`
const plotlyDiv = ref<HTMLElement>()
const noData = ref(false)
var plotlyHTMLElement
var plotlyLayout = computed(() => {
  if (!props.specgmQuery) return {}
  return {
    title: {
      text: props.specgmQuery.source_name +' - '+ (startChan.value * CHAN_BW_HZ / 1e6 + nChans.value * chanBwHz.value/2/1e6).toFixed(2) + ' MHz | LWA-Sevilleta',
      font: {
        family: 'Courier New, monospace',
        size: 24,
        color: colorMode.value == 'dark' ? 'white' : 'black'
      }
    },
    xaxis: {
      title: {
        text: `Time (${plotlyAxes.xLabels.length ? tz.zoneName(plotlyAxes.xLabels[0]) : tz.zoneName()})`,
        font: {
          family: 'Courier New, monospace',
          size: 18,
          color: colorMode.value == 'dark' ? 'white' : 'black'
        }
      },
      tickfont: {
        color: colorMode.value == 'dark' ? 'white' : 'black',
        family: 'Courier New, monospace'
      },
      tickcolor: colorMode.value == 'dark' ? 'white' : 'black',
      // keep the axes on the heatmap when the dispersion curve is drawn
      range: plotlyAxes.xLabels.length ? [tz.plotTime(plotlyAxes.xLabels[0]), tz.plotTime(plotlyAxes.xLabels[plotlyAxes.xLabels.length - 1])] : undefined
    },
    yaxis: {
      range: plotlyAxes.yLabels.length
        ? [plotlyAxes.yLabels[0] - chanBwHz.value / 2e6, plotlyAxes.yLabels[plotlyAxes.yLabels.length - 1] + chanBwHz.value / 2e6]
        : undefined,
      title: {
        text: 'Frequency (MHz)',
        font: {
          family: 'Courier New, monospace',
          size: 18,
          color: colorMode.value == 'dark' ? 'white' : 'black'
        }
      },
      tickfont: {
        color: colorMode.value == 'dark' ? 'white' : 'black'
      },
      tickcolor: colorMode.value == 'dark' ? 'white' : 'black'
    },
    paper_bgcolor: colorMode.value == 'dark' ? '#131826' : 'rgb(255,255,255)',
    // flagged samples are gaps in the heatmap; show them as neutral grey
    plot_bgcolor: colorMode.value == 'dark' ? '#374151' : '#d1d5db',
    hovermode: false,
    showlegend: false
  }
})

// Expected frequency of the burst over the displayed window, sampled in time
// since it can drift by less than a channel in a window. Channels are drawn at
// their lower edge, so the curve is offset by half a channel to match.
const dispersionTrace = computed(() => {
  const p = props.frb
  const x = plotlyAxes.xLabels
  const y = plotlyAxes.yLabels
  if (!p || !showDispersion.value || x.length < 2 || !y.length) return null
  const t0 = utcMs(x[0])
  const t1 = utcMs(x[x.length - 1])
  const half = chanBwHz.value / 2e6
  const pts = []
  for (let i = 0; i <= 300; i++) {
    const t = t0 + (t1 - t0) * i / 300
    const f = freqAtMs(p, t) - half
    if (f >= y[0] - half && f <= y[y.length - 1] + half) pts.push({ t, f })
  }
  if (!pts.length) return null
  return {
    x: pts.map(d => tz.plotTime(d.t)),
    y: pts.map(d => d.f),
    type: 'scatter', mode: 'lines',
    line: { dash: 'dash', width: 1.5, color: colorMode.value == 'dark' ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' }
  }
})

var plotlyConfig = computed(() => {
  return {
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'zoom2d', 'pan2d', ' zoomIn2d', 'zoomOut2d', 'autoScale2d', 'zoomIn'],
    toImageButtonOptions: {
      format: 'png', // one of png, svg, jpeg, webp
      filename: 'EPIC Spectrogram - ' + props.specgmQuery.source_name,
      scale: 3
    }
  }
})

// Colour range from the 1st to 99th percentiles of the samples shown (flagged
// ones excluded), so a few bright samples of leftover RFI do not compress
// the rest; no colour bar, since the images are not calibrated
function robustRange(rows: Float32Array[]) {
  const v: number[] = []
  const n = rows.reduce((a, r) => a + r.length, 0)
  const step = Math.max(1, Math.floor(n / 20000))
  let k = 0
  for (const r of rows) for (let t = 0; t < r.length; t++, k++) if (k % step == 0 && isFinite(r[t])) v.push(r[t])
  if (v.length < 2) return {}
  v.sort((a, b) => a - b)
  return { zmin: v[Math.floor(0.01 * (v.length - 1))], zmax: v[Math.ceil(0.99 * (v.length - 1))] }
}

var plotlyTraces = computed(() => {
  return [{
    z: plotData.value, type: 'heatmap', x: plotlyAxes.xLabels.map(tz.plotTime), y: plotlyAxes.yLabels, hoverongaps: false,
    ...robustRange(plotData.value), showscale: false, colorscale: 'Viridis', zsmooth: 'fast'
  }, ...(dispersionTrace.value ? [dispersionTrace.value] : [])]
})




// const xx = ref<Array<number[]>>([[]])
// const yy = ref<Array<number[]>>([[]])
// const xx_yy = ref<Array<number[]>>([[]])




const displayModes = [{
  label: 'X∗X',
  value: 'xx'
}, {
  label: 'Y∗Y',
  value: 'yy'
}, {
  label: 'Stokes I',
  value: 'xx_yy'
}]

// const dataUpdaters = {
//   xx: specUtils.get_xx,
//   yy: specUtils.get_yy,
//   xx_yy: specUtils.get_stokes_I
// }
const selectedMode = ref('xx_yy')

const { pending, data: specgmDataBytes, error: error } = await useLazyAsyncData<SpecgmData[]>(
  'specfetch',
  () => $fetch(rtConfig.public.fastapiBase + '/imaging/spectrogram/',
    {
      query: {
        start_time: props.specgmQuery.start_time,
        end_time: props.specgmQuery.end_time,
        // session_id: props.specgmQuery.session_id,
        chan0: props.specgmQuery.chan0,
        source_name: props.specgmQuery.source_name,
        pixel_positions: props.specgmQuery.pixel_positions
      }
    })
  , {
    watch: [() => props.specgmQuery],
  }
)

watch(() => error, (n, _) => {
  if (n.value) {
    toast.add({ title: 'Unable to fetch the spectrogram', color: 'red' })
  }
})

function updatePlotData() {
  switch (selectedMode.value) {
    case 'xx':
      plotDataRaw = xx_data
      break
    case 'yy':
      plotDataRaw = yy_data
      break
    case 'xx_yy':
      plotDataRaw = stokes_I
      break
    // default:
    //   throw ('Invalid mode selection')
  }
}



function updatePlot() {
  if (plotDataRaw.length < 1) return
  // with Flag RFI on, draw only once this window's mask is ready, so the
  // unflagged data never flash up; the previous plot stays, dimmed
  if (rfiOn.value && !rfiMasks.value[selectedMode.value]) return
  // In a hidden tab the plot has no width and Plotly falls back to 700 px,
  // so wait until the tab is shown; the resize observer draws it then
  if (!plotlyDiv.value || plotlyDiv.value.clientWidth == 0) return
  plotData.value = new Array()
  //copy the data intp plotData
  for (const arr of plotDataRaw) {
    plotData.value.push(arr.slice())
  }
  const rfi = rfiOn.value ? rfiMasks.value[selectedMode.value] : undefined
  if (rfi) plotData.value.forEach((row, c) => { const m = rfi[c]; if (m) for (let t = 0; t < row.length; t++) if (!m[t]) row[t] = NaN })
  // plotData=pdata
  // let trace=plotlyTraces.value
  // let trace=[{
  //   z: pdata, type: 'heatmap', x: xLabels, y: yLabels,hoverongaps: false,
  //   colorbar: {
  //     exponentformat: 'e'
  //   }, colorscale: 'Viridis', zsmooth: 'best'
  // }]


  plotlyHTMLElement = Plotly.newPlot(plotlyDivId, plotlyTraces.value, plotlyLayout.value, plotlyConfig.value)
  // switch (selectedMode.value) {
  //   case 'xx':
  //     console.log('changing heatmap data')
  //     Plotly.newPlot(plotlyDivId, [{
  //       z: xx_data, type: 'heatmap', x: xLabels, y: yLabels,
  //       colorbar: {
  //         exponentformat: 'e'
  //       }, colorscale: 'Viridis', zsmooth: 'best', showscale: false
  //     }], layout) //heatmap.data = data0//[{z:Array.from(xx_data),type:'heatmap'}]
  //     break
  //   case 'yy':
  //     console.log('in yy')
  //     Plotly.newPlot(plotlyDivId, [{ z: yy_data, type: 'heatmap', x: xLabels, y: yLabels }], layout)
  //     break
  //   case 'xx_yy':
  //     Plotly.newPlot(plotlyDivId, [{ z: stokes_I, type: 'heatmap', x: xLabels, y: yLabels }], layout)
  //     break
  //   // default:
  //   //   throw ('Invalid mode selection')
  // }

  // 

}
watch(() => colorMode.value, (n, o) => {
  updatePlot()
})
watch(() => showDispersion.value, () => updatePlot())
watch(rfiOn, on => { if (on && !rfiMasks.value[selectedMode.value]) requestRfiMask(); else updatePlot() })
watch(tz.mode, () => updatePlot())

watch(() => specgmDataBytes.value, (newData, _) => {

  console.log('change in data')
  if (!newData) return
  noData.value = newData.length == 0
  if (noData.value) {
    // drop the previous window's plot rather than leave it on screen
    xx_data = []; yy_data = []; stokes_I = []; plotDataRaw = []
    if (plotlyDiv.value) Plotly.purge(plotlyDiv.value)
    return
  }
  raw_data = new Array<Float32Array>()
  for (let i = 0; i < newData.length; ++i) {
    raw_data.push(specUtils.base64ToFloat32Array(newData[i].pixel_values))
  }

  xx_data = specUtils.get_xx(raw_data, nPols.value)
  // console.log('xx size',xx_data.value.length, xx_data.value[0].length)
  yy_data = specUtils.get_yy(raw_data, nPols.value)
  stokes_I = specUtils.get_stokes_I(xx_data, yy_data)
  //console.log(xx_data)

  plotlyAxes.xLabels = new Array(raw_data.length)
  for (let i = 0; i < plotlyAxes.xLabels.length; ++i) {
    plotlyAxes.xLabels[i] = newData[i].img_time
  }

  plotlyAxes.yLabels = new Array(nChans.value)
  for (let i = 0; i < nChans.value; ++i) {
    plotlyAxes.yLabels[i] = (startChan.value) * CHAN_BW_HZ / 1e6 + i * chanBwHz.value / 1e6
  }


  // console.log(raw_data.value)
  //heatmap.value.data[0].z = xx_data.value
  rfiMasks.value = {}
  rfiPending.value = false
  rfiRequest++
  updatePlotData()
  updatePlot()
  requestRfiMask()

})



watch(() => selectedMode.value, (newMode, _) => {
  console.log('changing plotdata')
  updatePlotData()
  updatePlot()
  requestRfiMask()

})

// const testdata = ref([[1, 20, 30], [20, 1, 60], [30, 60, 1]])
// const heatmap = reactive({
//   data: [{
//     z: [[1, 20, 30], [20, 1, 60], [30, 60, 1]],
//     type:'heatmap'
//   }],
//   config: { scrollZoom: true, displayModeBar: true },
//   layout:{title:'test'}
// })




// const specgmDataNumeric = computed(()=>{
//   if(!specgmDataBytes?.value?.length) return [[]]
//   for(let i=0;i<specgmDataBytes.value.length;++i){

//   }
// })

const resizeConfig = {
  resizeObserver: {} as ResizeObserver,
  timeOutFunctionId: {} as NodeJS.Timeout
}

const setResizeObserver = () => {
  resizeConfig.resizeObserver = new ResizeObserver((entries) => {
    if (entries.every(e => e.contentRect.width == 0)) return
    // debounce the reset
    clearTimeout(resizeConfig.timeOutFunctionId);
    resizeConfig.timeOutFunctionId = setTimeout(() => {
      updatePlot();
    }, 100);
  });
}
// Observe the plot whenever its element appears; in this client-only async
// component it can be created after onMounted
watch(plotlyDiv, (el, old) => {
  if (old) resizeConfig.resizeObserver?.unobserve?.(old)
  if (!el) return
  if (!resizeConfig.resizeObserver?.observe) setResizeObserver()
  resizeConfig.resizeObserver.observe(el)
}, { immediate: true })

onBeforeUnmount(() => {
  resizeConfig.resizeObserver.disconnect?.();
});

</script>

<template>
  <div>

    <!-- {{ pending }} <span v-if="plotData"> {{ plotData.length }}</span> -->
    <UCard :ui="{ body: { padding: 'px-2 py-2 sm:p-2 m-2' } }">
      <div class="flex flex-wrap justify-center items-center gap-x-10 gap-y-2">
        <div class="flex justify-center space-x-4 items-center">
          <span class="text-sm">Mode</span>
          <USelect v-model="selectedMode" :options="displayModes" option-attribute="label" value-attribute="value" />
        </div>
        <div class="flex items-center gap-x-6">
          <UCheckbox v-if="frb" v-model="showDispersion" label="Dispersion curve" />
          <div class="flex items-center gap-2">
            <UCheckbox v-model="rfiOn" label="Flag RFI" />
            <!-- always present and only shown or hidden: swapping them in and out with v-if broke Vue's patching here -->
            <UIcon v-show="rfiOn && rfiPending" name="i-heroicons-arrow-path-20-solid" class="w-4 h-4 animate-spin text-gray-500" />
            <span v-show="rfiOn && !rfiPending && rfiFlagged !== null" class="text-xs text-gray-500 dark:text-gray-400 tabular-nums">{{ rfiFlagged?.toFixed(1) }}% flagged</span>
          </div>
        </div>
      </div>
    </UCard>


    <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-1 m-1' } }" class="relative">
      <UProgress v-if="pending || (rfiOn && rfiPending)" animation="elastic" size="xs" class="p-0 m-0 top-0 left-0 absolute" />
      <p v-if="noData && !pending" class="p-4 text-sm text-gray-500 dark:text-gray-400">No images of the source were stored in this window.</p>
      <div :id="plotlyDivId" ref="plotlyDiv" class="transition-opacity" :class="rfiOn && rfiPending ? 'opacity-40' : ''"></div>
    
    </UCard>

  </div>
</template>