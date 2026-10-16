// RFI mask of a dynamic spectrum, ported from the FRB analysis
// (server/backend/app/frb/rfi.py), which follows the CHIME/FRB L1 chain
// (Rafiei-Ravandi & Smith 2023): standard-deviation and intensity clippers
// iterated, with Legendre detrending in time and frequency between the
// passes. Only the mask is returned; the display keeps the original values.
// It gives the same mask as the Python code.
//
// Data are time-major, x[t * nf + f], as in the Python code (x[t, f]). The
// loops work on flat typed arrays, with no per-sample allocation, so a
// 3-minute window runs in a fraction of a second in a worker.

const N_ITER = 6
const STDV_SIGMA = 3.0
const INTENSITY_SIGMA = 5.0
const INNER_ITER = 9
const DEGREE = 4
const K = DEGREE + 1
const MIN_CHUNK = 64

type Mask = Uint8Array

// median of the first n values of a scratch array, which it sorts
function median(v: Float64Array, n = v.length) {
  if (!n) return NaN
  const s = v.subarray(0, n).sort()
  const m = n >> 1
  return n % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

// Mean and std along an axis (0: per channel over time, 1: per sample over
// frequency, -1: all) from the unmasked values, iteratively clipped
function clippedStats(x: Float64Array, mask: Mask, nt: number, nf: number, axis: number, inner: number) {
  const nOut = axis == 0 ? nf : axis == 1 ? nt : 1
  const mean = new Float64Array(nOut), std = new Float64Array(nOut)
  const s = new Float64Array(nOut), n = new Float64Array(nOut), q = new Float64Array(nOut)
  let m = mask.slice()
  const next = new Uint8Array(m.length)
  for (let it = 0; it < INNER_ITER; it++) {
    s.fill(0); n.fill(0); q.fill(0)
    for (let t = 0, i = 0; t < nt; t++) for (let f = 0; f < nf; f++, i++) {
      if (!m[i]) continue
      const k = axis == 0 ? f : axis == 1 ? t : 0
      s[k] += x[i]; n[k]++
    }
    for (let k = 0; k < nOut; k++) mean[k] = n[k] > 0 ? s[k] / n[k] : NaN
    for (let t = 0, i = 0; t < nt; t++) for (let f = 0; f < nf; f++, i++) {
      if (!m[i]) continue
      const k = axis == 0 ? f : axis == 1 ? t : 0
      const d = x[i] - mean[k]; q[k] += d * d
    }
    for (let k = 0; k < nOut; k++) std[k] = n[k] > 1 ? Math.sqrt(q[k] / n[k]) : NaN
    let changed = false
    for (let t = 0, i = 0; t < nt; t++) for (let f = 0; f < nf; f++, i++) {
      const k = axis == 0 ? f : axis == 1 ? t : 0
      next[i] = mask[i] && Math.abs(x[i] - mean[k]) <= inner * std[k] ? 1 : 0
      if (next[i] != m[i]) changed = true
    }
    if (!changed) break
    m.set(next)
  }
  return { mean, std }
}

// Mask samples more than INTENSITY_SIGMA from the mean along an axis, after
// block-averaging by dt samples and df channels
function intensityClip(x: Float64Array, mask: Mask, nt: number, nf: number, axis: number, inner: number, dt = 1, df = 1) {
  const ntd = Math.floor(nt / dt), nfd = Math.floor(nf / df)
  let xd = x, md = mask
  if (dt > 1 || df > 1) {
    xd = new Float64Array(ntd * nfd)
    const wd = new Float64Array(ntd * nfd)
    for (let t = 0; t < ntd * dt; t++) {
      const row = Math.floor(t / dt) * nfd
      for (let f = 0; f < nfd * df; f++) {
        const i = t * nf + f
        if (mask[i]) { const j = row + Math.floor(f / df); xd[j] += x[i]; wd[j]++ }
      }
    }
    md = new Uint8Array(ntd * nfd)
    for (let j = 0; j < xd.length; j++) if (wd[j] > 0) { xd[j] /= wd[j]; md[j] = 1 }
  }
  const { mean, std } = clippedStats(xd, md, ntd, nfd, axis, inner)
  const out = mask.slice()
  for (let td = 0, j = 0; td < ntd; td++) for (let fd = 0; fd < nfd; fd++, j++) {
    const k = axis == 0 ? fd : axis == 1 ? td : 0
    if (!md[j] || !(Math.abs(xd[j] - mean[k]) > INTENSITY_SIGMA * std[k])) continue
    for (let t = td * dt; t < (td + 1) * dt; t++) for (let f = fd * df; f < (fd + 1) * df; f++) out[t * nf + f] = 0
  }
  return out
}

// Mask rows whose spread is an outlier among all rows (median and MAD of the
// spreads). Along time each channel is judged per block of samples; along
// frequency whole samples are masked.
function stdvClip(x: Float64Array, mask: Mask, nt: number, nf: number, axis: number, block = 256) {
  const starts: number[] = []
  if (axis == 0) {
    for (let a = 0; a < nt; a += block) starts.push(a)
    if (starts.length > 1 && nt - starts[starts.length - 1] < block / 2) starts.pop()
  }
  const nG = axis == 0 ? starts.length * nf : nt
  const v = new Float64Array(nG)
  // group g covers samples t in [a, b) of channels f in [f0, f1)
  const lim = new Int32Array(4)
  const bounds = (g: number) => {
    if (axis != 0) { lim[0] = g; lim[1] = g + 1; lim[2] = 0; lim[3] = nf; return }
    const s = Math.floor(g / nf)
    lim[0] = starts[s]; lim[1] = s + 1 < starts.length ? starts[s + 1] : nt; lim[2] = g % nf; lim[3] = lim[2] + 1
  }
  for (let g = 0; g < nG; g++) {
    bounds(g)
    let s = 0, n = 0
    for (let t = lim[0]; t < lim[1]; t++) for (let f = lim[2]; f < lim[3]; f++) { const i = t * nf + f; if (mask[i]) { s += x[i]; n++ } }
    if (n <= 8) { v[g] = NaN; continue }
    const mu = s / n
    let q = 0
    for (let t = lim[0]; t < lim[1]; t++) for (let f = lim[2]; f < lim[3]; f++) { const i = t * nf + f; if (mask[i]) { const d = x[i] - mu; q += d * d } }
    v[g] = q / n
  }
  const scratch = new Float64Array(nG)
  let nOk = 0
  for (let g = 0; g < nG; g++) if (isFinite(v[g])) scratch[nOk++] = v[g]
  if (nOk < 3) return mask
  const med = median(scratch, nOk)
  nOk = 0
  for (let g = 0; g < nG; g++) if (isFinite(v[g])) scratch[nOk++] = Math.abs(v[g] - med)
  const scale = 1.4826 * median(scratch, nOk)
  const out = mask.slice()
  for (let g = 0; g < nG; g++) {
    if (isFinite(v[g]) && !(scale > 0 && Math.abs(v[g] - med) > STDV_SIGMA * scale)) continue
    bounds(g)
    for (let t = lim[0]; t < lim[1]; t++) for (let f = lim[2]; f < lim[3]; f++) out[t * nf + f] = 0
  }
  return out
}

function count(m: Mask) {
  let n = 0
  for (let i = 0; i < m.length; i++) n += m[i]
  return n
}

function clippingChain(x: Float64Array, mask: Mask, nt: number, nf: number) {
  for (let it = 0; it < N_ITER; it++) {
    const before = count(mask)
    for (const axis of [0, 0, 0, 1, 1]) mask = stdvClip(x, mask, nt, nf, axis)
    mask = intensityClip(x, mask, nt, nf, 1, 5.0)
    mask = intensityClip(x, mask, nt, nf, 0, 5.0)
    mask = intensityClip(x, mask, nt, nf, -1, 3.0, 16, 2)
    mask = intensityClip(x, mask, nt, nf, 1, 3.0, 16, 2)
    if (count(mask) == before) break
  }
  return mask
}

// the Legendre basis P0..P4 on n points spanning [-1, 1], flat [j * K + r],
// computed once per length
const basisCache = new Map<number, Float64Array>()
function basisFor(n: number) {
  let b = basisCache.get(n)
  if (b) return b
  b = new Float64Array(n * K)
  for (let j = 0; j < n; j++) {
    const u = n > 1 ? -1 + 2 * j / (n - 1) : 0
    b[j * K] = 1; b[j * K + 1] = u
    for (let r = 1; r < DEGREE; r++) b[j * K + r + 1] = ((2 * r + 1) * u * b[j * K + r] - r * b[j * K + r - 1]) / (r + 1)
  }
  basisCache.set(n, b)
  return b
}

// solve the K x K system a c = b in place (Gaussian elimination with partial
// pivoting); false if singular
const ga = new Float64Array(K * K), gb = new Float64Array(K), coef = new Float64Array(K)
function solve() {
  for (let c = 0; c < K; c++) {
    let p = c
    for (let r = c + 1; r < K; r++) if (Math.abs(ga[r * K + c]) > Math.abs(ga[p * K + c])) p = r
    if (Math.abs(ga[p * K + c]) < 1e-12) return false
    if (p != c) {
      for (let j = 0; j < K; j++) { const tmp = ga[c * K + j]; ga[c * K + j] = ga[p * K + j]; ga[p * K + j] = tmp }
      const tb = gb[c]; gb[c] = gb[p]; gb[p] = tb
    }
    for (let r = 0; r < K; r++) {
      if (r == c) continue
      const k = ga[r * K + c] / ga[c * K + c]
      for (let j = c; j < K; j++) ga[r * K + j] -= k * ga[c * K + j]
      gb[r] -= k * gb[c]
    }
  }
  for (let r = 0; r < K; r++) coef[r] = gb[r] / ga[r * K + r]
  return true
}

// Fit a weighted Legendre polynomial to n samples starting at index i0 with
// a stride, and subtract it; when the fit fails, mask the samples instead
function fitSubtract(x: Float64Array, mask: Mask, i0: number, stride: number, n: number) {
  const b = basisFor(n)
  ga.fill(0); gb.fill(0)
  let w = 0
  for (let j = 0, i = i0; j < n; j++, i += stride) {
    if (!mask[i]) continue
    w++
    const o = j * K
    for (let r = 0; r < K; r++) {
      gb[r] += b[o + r] * x[i]
      for (let c = 0; c < K; c++) ga[r * K + c] += b[o + r] * b[o + c]
    }
  }
  if (w <= K || !solve()) {
    for (let j = 0, i = i0; j < n; j++, i += stride) mask[i] = 0
    return
  }
  for (let j = 0, i = i0; j < n; j++, i += stride) {
    const o = j * K
    let y = 0
    for (let r = 0; r < K; r++) y += b[o + r] * coef[r]
    x[i] -= y
  }
}

// subtract a polynomial along time in chunks, then one along frequency
function detrend(x: Float64Array, mask: Mask, nt: number, nf: number, chunk: number) {
  x = x.slice(); mask = mask.slice()
  for (let f = 0; f < nf; f++)
    for (let t0 = 0; t0 < nt; t0 += chunk) fitSubtract(x, mask, t0 * nf + f, nf, Math.min(nt, t0 + chunk) - t0)
  for (let t = 0; t < nt; t++) fitSubtract(x, mask, t * nf, 1, nf)
  return { x, mask }
}

// each channel scaled to unit robust spread over its unmasked samples
function restandardise(x: Float64Array, mask: Mask, nt: number, nf: number) {
  const out = x.slice()
  const v = new Float64Array(nt)
  for (let f = 0; f < nf; f++) {
    let n = 0
    for (let t = 0; t < nt; t++) if (mask[t * nf + f]) v[n++] = x[t * nf + f]
    const med = median(v, n)
    for (let j = 0; j < n; j++) v[j] = Math.abs(v[j] - med)
    const mad = 1.4826 * median(v, n)
    if (isFinite(mad) && mad > 0) for (let t = 0; t < nt; t++) out[t * nf + f] = (x[t * nf + f] - med) / mad
  }
  return out
}

// Whole channels that stand out from their neighbours in frequency, judged on
// the raw values: a typical level (median over time) or a spread over time
// (MAD) more than CHANNEL_SIGMA robust standard deviations above a running
// median across CHANNEL_WINDOW channels. The CHIME chain standardises each
// channel first, so a steady carrier or a line that switches on and off
// looks ordinary to it; in a picture they are the most visible RFI. Not part
// of the FRB analysis, where a steady offset is removed anyway.
const CHANNEL_SIGMA = 5
const CHANNEL_WINDOW = 7
function channelClip(x: Float64Array, mask: Mask, nt: number, nf: number) {
  const level = new Float64Array(nf).fill(NaN), spread = new Float64Array(nf).fill(NaN)
  const v = new Float64Array(nt)
  for (let f = 0; f < nf; f++) {
    let n = 0
    for (let t = 0; t < nt; t++) if (mask[t * nf + f]) v[n++] = x[t * nf + f]
    if (n < 8) continue
    const med = median(v, n)
    for (let j = 0; j < n; j++) v[j] = Math.abs(v[j] - med)
    level[f] = med
    spread[f] = 1.4826 * median(v, n)
  }
  const bad = new Uint8Array(nf)
  const scratch = new Float64Array(nf)
  for (const [a, twoSided] of [[level, true], [spread, false]] as const) {
    const r = new Float64Array(nf).fill(NaN)
    const h = CHANNEL_WINDOW >> 1
    for (let f = 0; f < nf; f++) {
      if (!isFinite(a[f])) continue
      let n = 0
      for (let g = Math.max(0, f - h); g <= Math.min(nf - 1, f + h); g++) if (isFinite(a[g])) scratch[n++] = a[g]
      r[f] = a[f] - median(scratch, n)
    }
    let n = 0
    for (let f = 0; f < nf; f++) if (isFinite(r[f])) scratch[n++] = Math.abs(r[f])
    const sig = 1.4826 * median(scratch, n)
    if (!(sig > 0)) continue
    for (let f = 0; f < nf; f++) if (isFinite(r[f]) && (twoSided ? Math.abs(r[f]) : r[f]) > CHANNEL_SIGMA * sig) bad[f] = 1
  }
  for (let f = 0; f < nf; f++) if (bad[f]) for (let t = 0; t < nt; t++) mask[t * nf + f] = 0
}

// Mask of good samples (1) for channels[f][t], as channel-major rows. With
// channelClip, whole outlying channels are masked first (see channelClip).
export function rfiMask(channels: ArrayLike<number>[], dtS: number, maxWidthS = 1.0, opts: { channelClip?: boolean } = {}): Uint8Array[] {
  const nf = channels.length, nt = channels[0]?.length ?? 0
  let x = new Float64Array(nt * nf)
  let mask: Mask = new Uint8Array(nt * nf)
  for (let f = 0; f < nf; f++) for (let t = 0; t < nt; t++) {
    const v = channels[f][t]
    if (isFinite(v)) { x[t * nf + f] = v; mask[t * nf + f] = 1 }
  }
  if (opts.channelClip) channelClip(x, mask, nt, nf)
  // static mask of dead channels, then standardise each channel
  const v = new Float64Array(nt)
  for (let f = 0; f < nf; f++) {
    let n = 0
    for (let t = 0; t < nt; t++) if (mask[t * nf + f]) v[n++] = x[t * nf + f]
    const med = median(v, n)
    for (let j = 0; j < n; j++) v[j] = Math.abs(v[j] - med)
    const mad = median(v, n)
    const dead = !isFinite(mad) || mad <= 0
    for (let t = 0; t < nt; t++) {
      const i = t * nf + f
      if (dead) { mask[i] = 0; x[i] = 0 } else x[i] = mask[i] ? (x[i] - med) / (1.4826 * mad) : 0
    }
  }
  const chunk = Math.max(MIN_CHUNK, Math.ceil(8 * maxWidthS / dtS))
  x = detrend(x, mask, nt, nf, chunk).x
  x = restandardise(x, mask, nt, nf)
  mask = clippingChain(x, mask, nt, nf)
  mask = detrend(x, mask, nt, nf, chunk).mask
  mask = clippingChain(x, mask, nt, nf)
  mask = detrend(x, mask, nt, nf, chunk).mask
  return Array.from({ length: nf }, (_, f) => {
    const row = new Uint8Array(nt)
    for (let t = 0; t < nt; t++) row[t] = mask[t * nf + f]
    return row
  })
}
