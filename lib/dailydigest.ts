import type { DailyDigestData, DailyDigestResp, DailyDigestTraceData } from '~/types';
import { CHAN_BW_HZ, DIGEST_CHAN_OFFSET } from '~/lib/ndp';

// sign(x)|x|^gamma: a plain power of a negative value is NaN for non-integer gamma
const signedPow = (x: number, gamma: number) => Math.sign(x) * Math.pow(Math.abs(x), gamma)

export function split_data_freq(resp: DailyDigestResp, gamma: number=1) {
  var out: { [cfreq: number]: DailyDigestTraceData } = {}
  if (!resp?.stats) return {}

  let stats = resp.stats
  let data = resp.data
  let nCFreqs = stats.length;
  let nChans = data[0].stokes_i.length
  let counter = 0

  // fractional powers of negative values are NaN and leave holes in the image
  if (gamma == undefined || !(Number(gamma) >= 1)) {
    gamma = 1
  }

  for (let ifreq = 0; ifreq < nCFreqs; ifreq++) {
    //console.log(ifreq)
    let cfreq = stats[ifreq].cfreq
    let nEpochs = stats[ifreq].count

    let img_time: string[] = new Array()
    let freqs: number[] = new Array()
    let stokes_I = new Array<Float32Array>()
    let stokes_V = new Array<Float32Array>()

    
    for (let i = 0; i < nChans; i++) {
      stokes_I.push(new Float32Array(nEpochs))
      stokes_V.push(new Float32Array(nEpochs))
    }

    let chan0 = Math.round(cfreq / CHAN_BW_HZ) - DIGEST_CHAN_OFFSET

    // the digest holds pairs of channels averaged together
    for (let i = 0; i < nChans; ++i) {
      freqs.push((chan0 + 2 * i) * CHAN_BW_HZ / 1e6)
    }

    for (let i = counter; i < counter+nEpochs; i++) {
      img_time.push(data[i].img_time)
      for (let j = 0; j < nChans; j++) {
        stokes_I[j][i-counter] = signedPow(data[i].stokes_i[j]/1e19,gamma)
        stokes_V[j][i-counter] = signedPow(data[i].stokes_v[j]/1e19,gamma)
      }
    }
    //console.log(img_time.length)
    out[cfreq] = {
      img_time: img_time,
      stokes_I: stokes_I,
      stokes_V: stokes_V,
      freqs: freqs
    }
    counter = counter + nEpochs
  }

  return out

}

export function get_stokes_I(data: DailyDigestData[]) {
  let img_time: string[] = []
  let stokes_I = new Array<Float32Array>()
  let stokes_V = new Array<Float32Array>()
  let nEpochs = data.length
  if (nEpochs == 0) {
    return {
      img_time: img_time,
      stokes_I: stokes_I,
      stokes_V: stokes_V
    }
  }
  let nChans = data[0].stokes_i.length

  for (let i = 0; i < nChans; i++) {
    stokes_I.push(new Float32Array(nEpochs))
    stokes_V.push(new Float32Array(nEpochs))
  }

  for (let i = 0; i < nEpochs; i++) {
    img_time.push(data[i].img_time)
    for (let j = 0; j < nChans; j++) {
      stokes_I[j][i] = data[i].stokes_i[j]
      stokes_V[j][i] = data[i].stokes_v[j]
    }
  }

  return {
    img_time: img_time,
    stokes_I: stokes_I,
    stokes_V: stokes_V
  }
}