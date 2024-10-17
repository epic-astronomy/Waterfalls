<script setup lang="ts">
import { format } from 'date-fns';
import type { DailyDigestSrc, DailyDigestSrcConfig, DailyDigestData } from '~/types';
import * as digestUtils from '~/lib/dailydigest'
import { v4 as uuidv4 } from "uuid"
import Plotly from 'plotly.js-dist-min'



const toast = useToast()
const colorMode = useColorMode()


const rtConfig = useRuntimeConfig() 

const digestDay = ref() 
const selectedSrc = ref('')
const chan_bw_hz = ref(50000)
const obsEnd = format((new Date().toISOString().slice(0, -1)), 'yyyy-MM-dd') // would be the current day
const selectedSrcConfigs = ref<{ [source: string]: number[] }>({}) // stores the observed frequencies for each source
const sourceNames = ref<String[]>([])


//////////////////////////////////
//Begin:  Source fetching based on date
//////////////////////////////////
const { pending, data: digestSrcs, error: error } = await useLazyAsyncData<DailyDigestSrc[]>(
  'dailysrcfetch',
  () => $fetch(rtConfig.public.fastapiBase + '/imaging/dailyobs/',
    {
      query: {
        day: digestDay.value
      }
    })
  , {
    watch: [() => digestDay.value],
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
  if(!n) return
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
  for(const obs of digestSrcs.value){
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
interface cfreqOpts{
  cfreq: number,
  label: string,
  chan0: number
}


const fetchTrigger = ref('')
const selectedCfreq = ref<cfreqOpts>()
const { pending: pending2, data: digestData, error: dataError } = await useLazyAsyncData<DailyDigestData[]>(
  'dailydatafetch',
  () => $fetch(rtConfig.public.fastapiBase + '/imaging/dailydigest/',
    {
      query: {
        day: digestDay.value,
        source_name: selectedSrc.value,
        cfreq: selectedCfreq?.value?.cfreq
      }
    })
  , {
    watch: [() => fetchTrigger.value],
    default: () => []
  }
)


const cfreqLabels = computed(()=>{
  if(selectedSrc.value=='' || !(selectedSrc.value in selectedSrcConfigs.value)) return []
  selectedCfreq.value = {}

  let cfreqs: cfreqOpts[] = []
  let nchan = 128*25000/chan_bw_hz.value
  for(const chan0 of selectedSrcConfigs.value[selectedSrc.value]){
    let cfreq_comp=(chan0+nchan/2-1)*25000
    let cfreq = chan0 * 0.025 + nchan * chan_bw_hz.value/2/1e6
    cfreqs.push({'cfreq':cfreq_comp, 'chan0':chan0, 'label':String((cfreq).toFixed(2))+ ' MHz'})
  }

  return cfreqs
  
})

const plotDataExists = computed(()=>{
  return plotData.value.length !=0
})

var stokes_I = Array<Float32Array>()
var stokes_V = Array<Float32Array>()
var raw_data = Array<Float32Array>()
var plotData = ref(Array<Float32Array>())
var plotDataRaw = Array<Float32Array>()
const plotlyDivId = `plotly-${uuidv4()}`

const plotlyAxes = reactive({
  xLabels: Array<string>(),
  yLabels: ref(Array<number>())
})

var plotlyHTMLElement
var plotlyLayout = computed(() => {
  if(!selectedCfreq.value) return
  let nChans = 128*25000/chan_bw_hz.value
  return {
    title: {
      text: selectedSrc.value +' - '+ (selectedCfreq.value?.chan0 * 0.025 + nChans * chan_bw_hz.value/2/1e6).toFixed(2) + ' MHz | LWA-Sevilleta',
      font: {
        family: 'Courier New, monospace',
        size: 24,
        color: colorMode.value == 'dark' ? 'white' : 'black'
      }
    },
    xaxis: {
      title: {
        text: 'Time (UTC)',
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
      tickcolor: colorMode.value == 'dark' ? 'white' : 'black'
    },
    yaxis: {
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
    paper_bgcolor: colorMode.value == 'dark' ? '#131826' : 'rgb(255,255,255)'
  }
})

var plotlyConfig = computed(() => {
  return {
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'zoom2d', 'pan2d', ' zoomIn2d', 'zoomOut2d', 'autoScale2d', 'zoomIn'],
    toImageButtonOptions: {
      format: 'png', // one of png, svg, jpeg, webp
      filename: 'EPIC Spectrogram - ' + selectedSrc.value,
      scale: 3
    }
  }
})

var plotlyTraces = computed(() => {
  return [{
    z: plotData.value, type: 'heatmap', x: plotlyAxes.xLabels, y: plotlyAxes.yLabels, hoverongaps: false,
    colorbar: {
      exponentformat: 'e',
      bordercolor: colorMode.value == 'dark' ? 'white' : 'black',
      tickcolor: colorMode.value == 'dark' ? 'white' : 'black',
      tickfont: {
        color: colorMode.value == 'dark' ? 'white' : 'black',
        family: 'Courier New, monospace'
      }
    }, colorscale: 'Viridis', zsmooth: 'best'
  }]
})

function updatePlot(){
  plotlyHTMLElement = Plotly.newPlot(plotlyDivId, plotlyTraces.value, plotlyLayout.value, plotlyConfig.value)
}


watch(()=>digestData.value, (newData,_)=>{
  if(!newData) return
  if(!selectedCfreq.value) return

  let res = digestUtils.get_stokes_I(newData)
  stokes_I = res.stokes_I
  stokes_V = res.stokes_V
  plotlyAxes.xLabels = res.img_time
  let nChans = 128*25000/chan_bw_hz.value
  plotlyAxes.yLabels = new Array(nChans)
  for (let i = 0; i < nChans; ++i) {
    plotlyAxes.yLabels[i] = (selectedCfreq.value?.chan0) * 0.025 + i * chan_bw_hz.value / 1e6
  }

  plotData.value=stokes_I
  updatePlot()
})

watch(() => dataError, (n, _) => {
  if (n.value) {
    toast.add({ title: 'Unable to fetch sources for the selected date.', color: 'red' })
  }
})

watch(() => colorMode.value, (n, o) => {
  updatePlot()
})

function displayData(){
  if(selectedSrc.value!='' && selectedCfreq.value!=undefined){
    fetchTrigger.value = selectedSrc.value+selectedCfreq.value.label
  }
}

const fetchDataDisabled = computed(()=>{
  return selectedSrc.value == '' || selectedCfreq.value ==undefined || !("cfreq" in selectedCfreq.value)? true: false
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
          <span class="text-md">Day (UTC): </span>
          <UInput type="date" v-model="digestDay" step=1 min="2024-10-16" :max="obsEnd"></UInput>
        </div>
        <div class="flex flex-wrap justify-center items-center gap-2">
          <span class="text-md"> Source: </span>
          <USelect v-model="selectedSrc" :options="sourceNames" placeholder="Select a source">
          </USelect>
        </div>
        <div class="flex flex-wrap justify-center items-center gap-2">
          <span class="text-md"> Frequency: </span>
          <USelectMenu v-model="selectedCfreq" :options="cfreqLabels" option-attribute="label" placeholder="Select Frequency">
          </USelectMenu>
        </div>

        <UButton :ui="{ rounded: 'rounded-md' }" variant="outline" label="Display" @click="displayData"
          :disabled="fetchDataDisabled">
        </UButton>
      </div>
    </UCard>
    <div v-if="!fetchDataDisabled">
    <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-1 m-1' } }" class="relative">
      <div :id="plotlyDivId"></div>
    
    </UCard></div>
    <div v-else>
          <UCard>
            <UPageHero title="Please select  date -> source -> frequency to continue" align="center">
            </UPageHero>
          </UCard>

        </div>
  </UDashboardPanelContent>
</template>