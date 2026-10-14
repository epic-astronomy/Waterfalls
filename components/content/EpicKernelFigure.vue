<script setup lang="ts">
// Figure: architecture delta between the multi-kernel (Bifrost) and fused (epic++) imaging kernels.
// Two snapshots on identical 264 x 440 grids (pitch 4) with a central change ledger; viewBox 736 x 504.
type Status = 'unchanged' | 'changed'
interface Comp { id: string, y: number, kind: 'input' | 'process' | 'store', name: string, status: Status, before: [string, string], after: [string, string] }
interface Rel { id: string, from: string, to: string, d: string, status: Status, before: [string, string], after: [string, string], labelY: number }

const X = 40
const W = 184
const H = 44

// [signature, sublabel] per snapshot
const comps: Comp[] = [
  { id: 'volt', y: 12, kind: 'input', name: 'F-engine voltages', status: 'unchanged',
    before: ['voltages;4+4bit;mem=global', 'global memory · 4+4 bit'], after: ['voltages;4+4bit;mem=global', 'global memory · 4+4 bit'] },
  { id: 'grid', y: 88, kind: 'process', name: 'Gridding', status: 'changed',
    before: ['grid;mem=global;clear=memset', 'global grid · memset'], after: ['grid;mem=shared;half-grid', 'shared-memory half grid'] },
  { id: 'fft', y: 164, kind: 'process', name: '2-D FFT', status: 'changed',
    before: ['fft;impl=cufft;mem=global', 'cuFFT · global memory'], after: ['fft;impl=cufftdx;mem=registers', 'cuFFTDx · registers'] },
  { id: 'mult', y: 240, kind: 'process', name: 'Cross-multiply', status: 'changed',
    before: ['xmult;kernel=separate', 'separate kernel'], after: ['xmult;kernel=fused;mem=registers', 'in registers'] },
  { id: 'acc', y: 316, kind: 'process', name: 'Accumulate', status: 'changed',
    before: ['acc;mem=global', 'global reduction'], after: ['acc;mem=registers;fp32', 'fp32 registers'] },
  { id: 'img', y: 392, kind: 'store', name: 'Image output', status: 'unchanged',
    before: ['image;float4;mem=global', 'global · float4 per pixel'], after: ['image;float4;mem=global', 'global · float4 per pixel'] }
]

// [signature, arrow label] per snapshot; empty label = unlabeled
const rels: Rel[] = [
  { id: 'volt-grid', from: 'volt', to: 'grid', d: 'M132,56 V88', status: 'unchanged', before: ['read', ''], after: ['read', ''], labelY: 0 },
  { id: 'grid-fft', from: 'grid', to: 'fft', d: 'M132,132 V164', status: 'changed', before: ['via=global', 'GLOBAL MEMORY'], after: ['via=shared', 'SHARED MEMORY'], labelY: 142 },
  { id: 'fft-mult', from: 'fft', to: 'mult', d: 'M132,208 V240', status: 'changed', before: ['via=global', 'GLOBAL MEMORY'], after: ['via=registers', 'REGISTERS'], labelY: 218 },
  { id: 'mult-acc', from: 'mult', to: 'acc', d: 'M132,284 V316', status: 'changed', before: ['via=global', 'GLOBAL MEMORY'], after: ['via=registers', 'REGISTERS'], labelY: 294 },
  { id: 'acc-img', from: 'acc', to: 'img', d: 'M132,360 V392', status: 'unchanged', before: ['write', ''], after: ['write', ''], labelY: 0 }
]

const ledger: { target: string, title: string, lines: [string, string] }[] = [
  { target: 'grid', title: 'Gridding', lines: ['global grid + memset →', 'half grid, shared memory'] },
  { target: 'fft', title: '2-D FFT', lines: ['cuFFT kernel →', 'cuFFTDx in registers'] },
  { target: 'mult', title: 'Cross-multiply', lines: ['separate kernel →', 'products in registers'] },
  { target: 'acc', title: 'Accumulate', lines: ['global reduction →', 'fp32 registers'] },
  { target: 'grid-fft', title: 'grid → FFT', lines: ['global memory →', 'shared memory'] },
  { target: 'fft-mult', title: 'FFT → multiply', lines: ['global memory →', 'registers'] },
  { target: 'mult-acc', title: 'multiply → accum.', lines: ['global memory →', 'registers'] }
]

const snapshots = [
  { key: 'before' as const, x: 24, heading: 'BEFORE · SEPARATE KERNELS' },
  { key: 'after' as const, x: 448, heading: 'AFTER · FUSED KERNEL' }
]

const nodeClass = (k: Comp['kind']) => k === 'process' ? 'ef-node' : `ef-node ef-node--${k}`
const labelWidth = (t: string) => Math.ceil((t.length * 0.62 * 8 + 8) / 4) * 4
</script>

<template>
  <figure class="ef-figure">
    <div class="ef-scroll">
      <svg
        data-diagram="architecture-delta"
        viewBox="0 0 736 504"
        role="img"
        aria-labelledby="epic-kernel-title epic-kernel-desc"
        xmlns="http://www.w3.org/2000/svg"
      >
        <title id="epic-kernel-title">Separate versus fused imaging kernels</title>
        <desc id="epic-kernel-desc">
          In the multi-kernel implementation, gridding, FFT, cross-multiplication and accumulation exchange data
          through GPU global memory; in the fused kernel the same stages run within one thread block per channel,
          exchanging data through shared memory and registers.
        </desc>
        <defs>
          <marker id="efk-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon class="ef-head" points="0 0, 8 3, 0 6" />
          </marker>
        </defs>

        <rect class="ef-bg" width="736" height="504" />

        <text
          v-for="s in snapshots" :key="`h-${s.key}`"
          class="ef-eyebrow" :x="s.x + 132" y="36" text-anchor="middle"
        >{{ s.heading }}</text>

        <g
          v-for="s in snapshots" :key="s.key"
          :data-snapshot="s.key" data-grid="264 440 4" :transform="`translate(${s.x} 48)`"
        >
          <!-- on-chip region of the fused kernel (zone, drawn first) -->
          <template v-if="s.key === 'after'">
            <rect class="ef-zone" x="24" y="60" width="216" height="308" rx="8" />
            <rect class="ef-mask" x="32" y="64" width="44" height="12" rx="2" />
            <text class="ef-zone-label" x="54" y="73" text-anchor="middle">ON-CHIP</text>
          </template>

          <!-- relationships -->
          <path
            v-for="r in rels" :key="`${s.key}-${r.id}`"
            class="ef-wire" :d="r.d" marker-end="url(#efk-arrow)"
            data-kind="relationship" :data-object-id="r.id" :data-status="r.status"
            :data-signature="r[s.key][0]" :data-from="r.from" :data-to="r.to"
          />
          <template v-for="r in rels" :key="`${s.key}-${r.id}-label`">
            <g v-if="r[s.key][1]">
              <rect class="ef-mask" x="140" :y="r.labelY" :width="labelWidth(r[s.key][1])" height="12" rx="2" />
              <text class="ef-label" :x="140 + labelWidth(r[s.key][1]) / 2" :y="r.labelY + 9" text-anchor="middle">{{ r[s.key][1] }}</text>
            </g>
          </template>

          <!-- components -->
          <g
            v-for="c in comps" :key="`${s.key}-${c.id}`"
            data-kind="component" :data-object-id="c.id" :data-status="c.status" :data-signature="c[s.key][0]"
          >
            <rect class="ef-mask" :x="X" :y="c.y" :width="W" :height="H" rx="6" />
            <rect data-role="bounds" :class="nodeClass(c.kind)" :x="X" :y="c.y" :width="W" :height="H" rx="6" />
            <text class="ef-name" :x="X + W / 2" :y="c.y + 20" text-anchor="middle">{{ c.name }}</text>
            <text class="ef-sub" :x="X + W / 2" :y="c.y + 34" text-anchor="middle">{{ c[s.key][1] }}</text>
            <text v-if="c.status === 'changed'" class="ef-badge" :x="X + W - 12" :y="c.y + 16" text-anchor="middle">Δ</text>
          </g>
        </g>

        <!-- change ledger -->
        <text class="ef-eyebrow" x="304" y="72">CHANGES</text>
        <line class="ef-hair" x1="304" y1="80" x2="432" y2="80" />
        <text
          v-for="(e, i) in ledger" :key="`led-${e.target}`"
          data-change="CHANGED" :data-target="e.target" x="304" :y="100 + i * 44"
        >
          <tspan class="ef-ledger-key">CHANGED </tspan><tspan class="ef-ledger">{{ e.title }}</tspan>
          <tspan class="ef-ledger" x="304" dy="12">{{ e.lines[0] }}</tspan>
          <tspan class="ef-ledger" x="304" dy="11">{{ e.lines[1] }}</tspan>
        </text>
      </svg>
    </div>
    <figcaption>
      <strong>Figure 2.</strong> Imaging stages for one channel and one time sample in the multi-kernel Bifrost
      implementation (left) and the fused <code>epic++</code> kernel (right). In the fused kernel all intermediate
      products remain in shared memory or registers within a single thread block; global memory is accessed only to
      read voltages and to write accumulated images. Δ marks stages whose implementation differs.
    </figcaption>
  </figure>
</template>
