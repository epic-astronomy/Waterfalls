import type { DailyDigestData } from '~/types';

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