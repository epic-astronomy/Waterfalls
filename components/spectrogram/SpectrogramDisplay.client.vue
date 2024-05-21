<script setup lang="ts">
import type { PropType } from 'vue';
import type { SpecgmData, SpecgmQuery } from '~/types'
import * as specUtils from '~/lib/spectrogram'
import Plotly from 'plotly.js-dist-min'
import { v4 as uuidv4 } from "uuid"

const toast = useToast()
const colorMode = useColorMode()


const rtConfig = useRuntimeConfig()
const props = defineProps<{
  specgmQuery: SpecgmQuery
}>()

// const startFreq = inject('startFreq')
// const nChans = inject('nChans')
// const chanBwHz = inject('chanBwHz')

const nChans = computed(() => props.specgmQuery.n_chan)
const startChan = computed(() => props.specgmQuery.start_chan)
const chanBwHz = computed(() => props.specgmQuery.chan_bw_hz)
const nPols = computed(() => props.specgmQuery.n_pols)
// const nBufElems = 128 * nPols
//const sourceName = 'PSR B1133+16'

interface flagChanOptType {
  id: number,
  label: string
}
const flagChans = ref<flagChanOptType[]>([])
var flagChansOptions = ref<flagChanOptType[]>([])
watch(()=>props.specgmQuery.start_chan,(n,o)=>{
  console.log('changed in startchan, nchans')
  if(n==o && flagChansOptions.value.length!=0) return
  let opts=[]
  for (let i = 0; i < props.specgmQuery.n_chan; ++i) {
    opts.push({
      id: i,
      label: (props.specgmQuery.start_chan * 0.025 + i * props.specgmQuery.chan_bw_hz / 1e6).toFixed(3) + ' MHz'
    })
  }
  flagChansOptions.value = opts
},{ immediate: true })

// computed(() => {
//   console.log('flag chan options ')
//   if (!props.specgmQuery) return
//   let opts = []
//   for (let i = 0; i < props.specgmQuery.n_chan; ++i) {
//     opts.push({
//       id: i,
//       label: (props.specgmQuery.start_chan * 0.025 + i * props.specgmQuery.chan_bw_hz / 1e6).toFixed(3) + ' MHz'
//     })
//   }
//   return opts
// })


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
var plotlyHTMLElement
var plotlyLayout = computed(() => {
  if (!props.specgmQuery) return {}
  return {
    title: {
      text: props.specgmQuery.source_name +' - '+ (startChan.value * 0.025 + nChans.value * chanBwHz.value/2/1e6).toFixed(2) + ' MHz | LWA-Sevilleta',
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
      filename: 'EPIC Spectrogram - ' + props.specgmQuery.source_name,
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
    }, colorscale: 'Viridis', zsmooth: 'fast'
  }]
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
  label: 'I = (X∗X + Y∗Y)',
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
        session_id: props.specgmQuery.session_id,
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
  plotData.value = new Array()
  //copy the data intp plotData
  for (const arr of plotDataRaw) {
    plotData.value.push(arr.slice())
  }
  for (const flag of flagChans.value) {
    console.log('flagging', flag.id, flagChans)
    if (flag.id >= 0) plotData.value[flag.id] = plotData.value[flag.id].fill(NaN)
  }
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
watch(() => flagChans.value, (n, o) => updatePlot())
watch(()=>props.specgmQuery.session_id,(n,o)=>{
  if(n!=o){
    console.log('change in session id')
    flagChans.value=[]
  }
})

watch(() => specgmDataBytes.value, (newData, _) => {

  console.log('change in data')
  if (!newData) return
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
    plotlyAxes.yLabels[i] = (startChan.value) * 0.025 + i * chanBwHz.value / 1e6
  }


  // console.log(raw_data.value)
  //heatmap.value.data[0].z = xx_data.value
  updatePlotData()
  updatePlot()

})



watch(() => selectedMode.value, (newMode, _) => {
  console.log('changing plotdata')
  updatePlotData()
  updatePlot()

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
  <div>

    <!-- {{ pending }} <span v-if="plotData"> {{ plotData.length }}</span> -->
    <UCard :ui="{ body: { padding: 'px-2 py-2 sm:p-2 m-2' } }">
      <div class="flex justify-between">
        <div class="flex justify-center space-x-4 items-center">
          <div>Mode: </div>
          <URadio v-for="mode of displayModes" :key="mode.value" v-model="selectedMode" v-bind="mode" legend="Show" />
        </div>
        <div class="flex justify-center space-x-4 items-center">
          <div> Flag: </div>
          <USelectMenu v-model="flagChans" :options="flagChansOptions" multiple>
            <template #label>
              <template v-if="flagChans.length">
                <span> {{ flagChans.length }} frequenc{{ flagChans.length > 1 ? 'ies' : 'y' }}</span>
              </template>
              <template v-else>
                <span class="text-gray-500 dark:text-gray-400 truncate">Select frequency</span>
              </template>
            </template>
          </USelectMenu>
        </div>
      </div>
    </UCard>


    <UCard :ui="{ body: { padding: 'px-1 py-1 sm:p-1 m-1' } }" class="relative">
      <UProgress v-if="pending" animation="elastic" size="xs" class="p-0 m-0 top-0 left-0 absolute" />
      <div :id="plotlyDivId"></div>
    
    </UCard>

  </div>
</template>