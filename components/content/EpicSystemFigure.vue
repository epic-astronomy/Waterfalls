<script setup lang="ts">
// Figure: architecture of the deployed EPIC system at LWA-SV (one compute node shown; six are deployed).
// Geometry on a 4px grid; viewBox 736 x 516. Colors come from assets/css/epic-figures.css.
type Kind = 'input' | 'process' | 'focal' | 'external' | 'store'
interface Node { x: number, y: number, kind: Kind, tag: string, name: string, sub: string }

const W = 164
const H = 56

const nodes: Node[] = [
  { x: 80, y: 24, kind: 'input', tag: 'SOURCE', name: 'Station F-engine', sub: '6 sub-bands · 100 GbE' },
  { x: 70, y: 128, kind: 'focal', tag: 'GPU', name: 'epic++ imager', sub: 'Nomad job · one per node' },
  { x: 70, y: 336, kind: 'process', tag: 'RTMP', name: 'Media server', sub: 'Node-Media-Server' },
  { x: 340, y: 128, kind: 'process', tag: 'CONTROL', name: 'Nomad · Consul · Vault', sub: 'jobs · config · secrets' },
  { x: 528, y: 128, kind: 'process', tag: 'GRPC', name: 'Watchdog', sub: 'watch-list service' },
  { x: 340, y: 232, kind: 'process', tag: 'METRICS', name: 'Monitoring', sub: 'Prometheus · Alertmanager' },
  { x: 528, y: 232, kind: 'store', tag: 'CITUS', name: 'Pixel database', sub: 'PostgreSQL · 7 nodes' },
  { x: 340, y: 336, kind: 'external', tag: 'WEB', name: 'EPIC TV', sub: 'PeerTube live stream' },
  { x: 528, y: 336, kind: 'external', tag: 'WEB', name: 'Waterfalls', sub: 'Nuxt · FastAPI' }
]

type Style = 'muted' | 'accent' | 'dash' | 'link'
const wires: { d: string, style: Style }[] = [
  { d: 'M152,80 V128', style: 'accent' }, // F-engine -> imager
  { d: 'M152,184 V336', style: 'muted' }, // imager -> media server
  { d: 'M234,364 H340', style: 'muted' }, // media server -> EPIC TV
  { d: 'M340,144 H234', style: 'dash' }, // control plane -> imager
  { d: 'M610,128 V120 Q610,112 602,112 H208 Q200,112 200,120 V128', style: 'muted' }, // watchdog -> imager
  { d: 'M234,172 H304 Q312,172 312,180 V200 Q312,208 320,208 H552 Q560,208 560,216 V232', style: 'muted' }, // imager -> DB
  { d: 'M610,232 V184', style: 'muted' }, // DB -> watchdog
  { d: 'M610,336 V288', style: 'muted' }, // waterfalls -> DB
  { d: 'M610,448 V392', style: 'link' } // external alerts -> waterfalls
]

const labels = [
  { x: 160, y: 90, w: 56, text: 'MULTICAST' },
  { x: 160, y: 254, w: 36, text: 'VIDEO' },
  { x: 273, y: 344, w: 28, text: 'RTMP' },
  { x: 251, y: 124, w: 72, text: 'CONFIGURATION' },
  { x: 420, y: 94, w: 56, text: 'WATCH LIST' },
  { x: 400, y: 190, w: 56, text: 'PIXEL ROWS' },
  { x: 618, y: 202, w: 64, text: 'WATCH TABLE' },
  { x: 618, y: 306, w: 44, text: 'QUERIES' }
]

const legend: { kind: Kind, text: string }[] = [
  { kind: 'input', text: 'INPUT' },
  { kind: 'focal', text: 'IMAGER' },
  { kind: 'process', text: 'SERVICE' },
  { kind: 'store', text: 'DATA STORE' },
  { kind: 'external', text: 'PUBLIC SERVICE' }
]

const wireClass = (s: Style) => ({
  muted: 'ef-wire',
  accent: 'ef-wire ef-wire--accent',
  dash: 'ef-wire ef-wire--dash',
  link: 'ef-wire ef-wire--link ef-wire--dash'
})[s]
const marker = (s: Style) => s === 'accent' ? 'url(#efs-arrow-accent)' : s === 'link' ? 'url(#efs-arrow-link)' : 'url(#efs-arrow)'
const nodeClass = (k: Kind) => k === 'process' ? 'ef-node' : `ef-node ef-node--${k}`
const tagWidth = (t: string) => Math.ceil((t.length * 0.62 * 7 + 8) / 4) * 4
</script>

<template>
  <figure class="ef-figure">
    <div class="ef-scroll">
      <svg
        viewBox="0 0 736 516"
        role="img"
        aria-labelledby="epic-system-title epic-system-desc"
        xmlns="http://www.w3.org/2000/svg"
      >
        <title id="epic-system-title">Architecture of the EPIC system at LWA-SV</title>
        <desc id="epic-system-desc">
          Each compute node runs an imager that receives F-engine data, takes its configuration and secrets from the
          control plane and its watch list from the watchdog, writes pixel rows to the distributed database, and sends
          video through a media server to EPIC TV; the Waterfalls application queries the database and records
          external alerts that the watchdog turns into watch-list entries.
        </desc>
        <defs>
          <marker id="efs-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon class="ef-head" points="0 0, 8 3, 0 6" />
          </marker>
          <marker id="efs-arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon class="ef-head ef-head--accent" points="0 0, 8 3, 0 6" />
          </marker>
          <marker id="efs-arrow-link" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon class="ef-head ef-head--link" points="0 0, 8 3, 0 6" />
          </marker>
        </defs>

        <rect class="ef-bg" width="736" height="516" />

        <!-- regions -->
        <rect class="ef-region" x="20" y="84" width="268" height="332" rx="8" />
        <rect class="ef-mask" x="28" y="88" width="100" height="12" rx="2" />
        <text class="ef-eyebrow" x="78" y="97" text-anchor="middle">COMPUTE NODE ×6</text>
        <rect class="ef-region" x="316" y="84" width="400" height="332" rx="8" />
        <rect class="ef-mask" x="324" y="88" width="84" height="12" rx="2" />
        <text class="ef-eyebrow" x="366" y="97" text-anchor="middle">COORDINATOR</text>

        <!-- connectors -->
        <path
          v-for="(w, i) in wires" :key="`w${i}`"
          :d="w.d" :class="wireClass(w.style)" :marker-end="marker(w.style)"
        />
        <g v-for="(l, i) in labels" :key="`l${i}`">
          <rect class="ef-mask" :x="l.x" :y="l.y" :width="l.w" height="12" rx="2" />
          <text class="ef-label" :x="l.x + l.w / 2" :y="l.y + 9" text-anchor="middle">{{ l.text }}</text>
        </g>
        <text class="ef-eyebrow" x="610" y="464" text-anchor="middle">CHIME/FRB ALERTS</text>

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
        <line class="ef-hair" x1="20" y1="480" x2="716" y2="480" />
        <text class="ef-eyebrow" x="20" y="504">LEGEND</text>
        <g v-for="(item, i) in legend" :key="`k${i}`">
          <rect :class="nodeClass(item.kind)" :x="88 + i * 124" y="496" width="16" height="10" rx="2" />
          <text class="ef-label" :x="88 + i * 124 + 22" y="504">{{ item.text }}</text>
        </g>
      </svg>
    </div>
    <figcaption>
      <strong>Figure 3.</strong> Architecture of the EPIC system at LWA-SV. One of the six identical compute nodes is
      shown. Dashed connectors denote configuration and external alerts. Prometheus collects metrics from every
      service, including the imager; those connectors are omitted for clarity.
    </figcaption>
  </figure>
</template>
