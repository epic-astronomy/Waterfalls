<script setup lang="ts">
// Figure: dataflow graph of the epic++ imager (one GPU instance).
// Geometry on a 4px grid; viewBox 736 x 432. Colors come from assets/css/epic-figures.css.
type Kind = 'input' | 'process' | 'focal' | 'external' | 'store'
interface Node { x: number, y: number, kind: Kind, tag: string, name: string, sub: string }

const W = 144
const H = 56

const nodes: Node[] = [
  { x: 20, y: 24, kind: 'input', tag: 'SOURCE', name: 'Station F-engine', sub: 'ADP · 25 kHz · 4+4 bit' },
  { x: 204, y: 24, kind: 'process', tag: 'CPU', name: 'Packet capture', sub: 'ibverbs · 40 ms gulps' },
  { x: 388, y: 24, kind: 'focal', tag: 'GPU', name: 'Imaging kernel', sub: 'grid · FFT · multiply' },
  { x: 572, y: 24, kind: 'process', tag: 'CPU', name: 'Video streamer', sub: 'Stokes I · H.264/RTMP' },
  { x: 388, y: 120, kind: 'process', tag: 'CPU', name: 'Channel reducer', sub: 'SIMD channel sum' },
  { x: 204, y: 216, kind: 'external', tag: 'GRPC', name: 'Watch list', sub: 'watchdog service' },
  { x: 388, y: 216, kind: 'process', tag: 'CPU', name: 'Pixel extractor', sub: '5×5 source patches' },
  { x: 572, y: 216, kind: 'store', tag: 'DB', name: 'Pixel database', sub: 'PostgreSQL' },
  { x: 388, y: 312, kind: 'store', tag: 'FILES', name: 'Image archive', sub: '1.28 s FITS cubes' }
]

// Straight orthogonal connectors (endpoints share an axis).
const wires = [
  { d: 'M164,52 H204', accent: false },
  { d: 'M348,52 H388', accent: true },
  { d: 'M532,52 H572', accent: false },
  { d: 'M460,80 V120', accent: false },
  { d: 'M460,176 V216', accent: false },
  { d: 'M348,244 H388', accent: false },
  { d: 'M532,244 H572', accent: false },
  { d: 'M460,272 V312', accent: false }
]

// Arrow labels: mask rect + text, 8px clear of the stroke.
const labels = [
  { x: 172, y: 32, w: 24, text: 'UDP' },
  { x: 350, y: 32, w: 36, text: 'GULPS' },
  { x: 468, y: 94, w: 68, text: '80 MS IMAGES' },
  { x: 468, y: 286, w: 40, text: 'IMAGES' }
]

const legend: { kind: Kind, text: string }[] = [
  { kind: 'input', text: 'INPUT' },
  { kind: 'process', text: 'CPU STAGE' },
  { kind: 'focal', text: 'GPU KERNEL' },
  { kind: 'external', text: 'SERVICE' },
  { kind: 'store', text: 'DATA STORE' }
]

const nodeClass = (k: Kind) => k === 'process' ? 'ef-node' : `ef-node ef-node--${k}`
const tagWidth = (t: string) => Math.ceil((t.length * 0.62 * 7 + 8) / 4) * 4
</script>

<template>
  <figure class="ef-figure">
    <div class="ef-scroll">
      <svg
        viewBox="0 0 736 432"
        role="img"
        aria-labelledby="epic-pipeline-title epic-pipeline-desc"
        xmlns="http://www.w3.org/2000/svg"
      >
        <title id="epic-pipeline-title">Dataflow of the epic++ imager</title>
        <desc id="epic-pipeline-desc">
          F-engine packets are captured and assembled into gulps, imaged on the GPU, channel-reduced,
          and cut into source patches using the watch list; patches go to the pixel database, full images
          to the FITS archive, and full-resolution Stokes I images to the video stream.
        </desc>
        <defs>
          <marker id="efp-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon class="ef-head" points="0 0, 8 3, 0 6" />
          </marker>
          <marker id="efp-arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon class="ef-head ef-head--accent" points="0 0, 8 3, 0 6" />
          </marker>
        </defs>

        <rect class="ef-bg" width="736" height="432" />

        <!-- connectors first, so nodes sit above them -->
        <path
          v-for="(w, i) in wires"
          :key="`w${i}`"
          :d="w.d"
          :class="w.accent ? 'ef-wire ef-wire--accent' : 'ef-wire'"
          :marker-end="w.accent ? 'url(#efp-arrow-accent)' : 'url(#efp-arrow)'"
        />
        <g v-for="(l, i) in labels" :key="`l${i}`">
          <rect class="ef-mask" :x="l.x" :y="l.y" :width="l.w" height="12" rx="2" />
          <text class="ef-label" :x="l.x + l.w / 2" :y="l.y + 9" text-anchor="middle">{{ l.text }}</text>
        </g>

        <!-- nodes -->
        <g v-for="(n, i) in nodes" :key="`n${i}`">
          <rect class="ef-mask" :x="n.x" :y="n.y" :width="W" :height="H" rx="6" />
          <rect :class="nodeClass(n.kind)" :x="n.x" :y="n.y" :width="W" :height="H" rx="6" />
          <rect
            :class="n.kind === 'focal' ? 'ef-tag ef-tag--focal' : 'ef-tag'"
            :x="n.x + 8" :y="n.y + 6" :width="tagWidth(n.tag)" height="12" rx="2"
          />
          <text
            :class="n.kind === 'focal' ? 'ef-tag-text ef-tag-text--focal' : 'ef-tag-text'"
            :x="n.x + 8 + tagWidth(n.tag) / 2" :y="n.y + 15" text-anchor="middle"
          >{{ n.tag }}</text>
          <text class="ef-name" :x="n.x + W / 2" :y="n.y + 34" text-anchor="middle">{{ n.name }}</text>
          <text class="ef-sub" :x="n.x + W / 2" :y="n.y + 48" text-anchor="middle">{{ n.sub }}</text>
        </g>

        <!-- legend strip -->
        <line class="ef-hair" x1="20" y1="388" x2="716" y2="388" />
        <text class="ef-eyebrow" x="20" y="412">LEGEND</text>
        <g v-for="(item, i) in legend" :key="`k${i}`">
          <rect :class="nodeClass(item.kind)" :x="88 + i * 128" y="404" width="16" height="10" rx="2" />
          <text class="ef-label" :x="88 + i * 128 + 22" y="412">{{ item.text }}</text>
        </g>
      </svg>
    </div>
    <figcaption>
      <strong>Figure 1.</strong> Dataflow graph of one instance of the <code>epic++</code> imager. Each stage executes on a
      dedicated CPU thread; the imaging kernel executes on the GPU. The video streamer receives full-resolution images,
      and all other products derive from the channel-reduced images.
    </figcaption>
  </figure>
</template>
