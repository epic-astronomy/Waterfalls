<script setup lang="ts">
// The candidates of the period in DM against arrival time, as in the
// single-pulse plots of PRESTO and Heimdall and the MeerTRAP labeller:
// one point per candidate, sized by S/N and coloured by class. A pulsar
// shows as a row at its DM (dashed, for the pulsars with pulses in the
// period) and interference as a column at one time. A click opens the
// candidate in the viewer.
import Plotly from 'plotly.js-dist-min'
import { v4 as uuidv4 } from 'uuid'
import { CRAB_DATA_URL, hasIcon } from '~/lib/pulsars'

interface Point {
  id: string, node: string, cls: string, snr: number, dm: number, t_inf: number,
  known_source?: { kind: string, name: string } | null
}
const props = defineProps<{
  cands: Point[],
  // pulsars to mark: name, short label and DM
  pulsars?: { name: string, label: string, dm: number }[],
  open?: { node: string, id: string } | null,
  // band names by node, for the hover text
  bands?: Record<string, string>
}>()
const emit = defineEmits<{ select: [c: Point] }>()

const colorMode = useColorMode()
const tz = useTimeZone()
const el = ref<HTMLElement>()
const divId = `skymon-dmt-${uuidv4()}`

const COLOURS: Record<string, string> = { candidate: '#f59e0b', injection: '#38bdf8', known: '#c084fc', rfi: '#9ca3af' }
const NAMES: Record<string, string> = { candidate: 'Candidate', injection: 'Test injection', known: 'Known source', rfi: 'RFI' }
const size = (snr: number) => Math.max(5, Math.min(26, 3 + 3 * Math.sqrt(Math.max(0, snr - 6))))

function draw() {
  const div = el.value
  if (!div || !div.clientWidth) return
  const dark = colorMode.value == 'dark'
  const ink = dark ? '#e5e7eb' : '#111827'
  const grid = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'
  const traces: any[] = []
  for (const cls of ['rfi', 'known', 'injection', 'candidate']) {
    const pts = props.cands.filter(c => c.cls == cls && c.dm > 0)
    if (!pts.length) continue
    traces.push({
      type: 'scatter', mode: 'markers', name: NAMES[cls],
      x: pts.map(c => tz.plotTime(c.t_inf * 1000)), y: pts.map(c => c.dm), customdata: pts.map(c => `${c.node}|${c.id}`),
      text: pts.map(c => `${props.bands?.[c.node] ?? ''} S/N ${c.snr.toFixed(1)}, DM ${c.dm.toFixed(1)}${c.known_source ? ', ' + c.known_source.name : ''}`),
      hovertemplate: '%{text}<br>%{x}<extra></extra>',
      marker: { size: pts.map(c => size(c.snr)), color: COLOURS[cls], opacity: cls == 'rfi' ? 0.45 : 0.85,
        line: { width: 0.5, color: dark ? '#111827' : '#ffffff' } }
    })
  }
  const o = props.open && props.cands.find(c => c.node == props.open!.node && c.id == props.open!.id)
  if (o) traces.push({ type: 'scatter', mode: 'markers', hoverinfo: 'skip', showlegend: false,
    x: [tz.plotTime(o.t_inf * 1000)], y: [o.dm],
    marker: { size: size(o.snr) + 10, color: 'rgba(0,0,0,0)', line: { width: 2.5, color: dark ? '#ffffff' : '#111827' } } })
  // the time span of the points, at least an hour, so a single candidate does not zoom to milliseconds
  const ts = props.cands.map(c => c.t_inf)
  const t0 = ts.length ? Math.min(...ts) : Date.now() / 1000 - 3600, t1 = ts.length ? Math.max(...ts) : Date.now() / 1000
  const pad = Math.max(0.04 * (t1 - t0), Math.max(0, 3600 - (t1 - t0)) / 2, 60)
  const shapes: any[] = [], annotations: any[] = [], images: any[] = []
  for (const p of props.pulsars ?? []) {
    shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: p.dm, y1: p.dm,
      line: { dash: 'dash', width: 1, color: '#c084fc' } })
    if (hasIcon(p.name)) images.push({ source: CRAB_DATA_URL, xref: 'paper', yref: 'y', x: 1.005, y: Math.log10(p.dm),
      sizex: 0.05, sizey: 0.25, xanchor: 'left', yanchor: 'middle', sizing: 'contain' })
    else annotations.push({ xref: 'paper', x: 1.005, y: Math.log10(p.dm), yref: 'y', text: p.label, showarrow: false,
      xanchor: 'left', font: { size: 10, color: '#c084fc' } })
  }
  Plotly.react(div, traces, {
    height: 260,
    margin: { t: 6, b: 40, l: 52, r: 74 },
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    xaxis: { title: { text: `Arrival (${tz.zoneName()})`, font: { size: 11, color: ink } },
      tickfont: { size: 10, color: ink }, gridcolor: grid, zeroline: false, tickformat: '%H:%M', nticks: 6,
      range: [tz.plotTime((t0 - pad) * 1000), tz.plotTime((t1 + pad) * 1000)] },
    yaxis: { type: 'log', title: { text: 'DM (pc cm⁻³)', font: { size: 11, color: ink } }, tickfont: { size: 10, color: ink },
      gridcolor: grid, zeroline: false, dtick: 1, range: [0, Math.log10(6000)] },
    showlegend: false, hovermode: 'closest', dragmode: 'zoom',
    shapes, annotations, images
  }, { displaylogo: false, responsive: true, displayModeBar: false })
    .then(bind)
}

// clicks, bound once the plot exists (it may first be drawn when its tab is shown)
let bound = false
function bind() {
  const div = el.value as any
  if (bound || !div?.on) return
  bound = true
  div.on('plotly_click', (ev: any) => {
    const cd = ev?.points?.[0]?.customdata
    if (typeof cd != 'string') return
    const i = cd.indexOf('|')
    const c = props.cands.find(x => x.node == cd.slice(0, i) && x.id == cd.slice(i + 1))
    if (c) emit('select', c)
  })
}

let ro: ResizeObserver | undefined
onMounted(() => {
  draw()
  ro = new ResizeObserver(() => draw())
  if (el.value) ro.observe(el.value)
})
onBeforeUnmount(() => { ro?.disconnect(); if (el.value) Plotly.purge(el.value) })
watch([() => props.cands, () => props.pulsars, () => props.open, colorMode, () => tz.mode.value], draw)
</script>

<template>
  <div :id="divId" ref="el" class="w-full" />
</template>
