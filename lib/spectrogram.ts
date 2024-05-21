export function base64ToFloat32Array(data: string) {

  const buf = atob(data)
  var view = new DataView(new ArrayBuffer(Float32Array.BYTES_PER_ELEMENT))
  var nelem = buf.length / Float32Array.BYTES_PER_ELEMENT

  var outArray = new Float32Array(nelem)

  for (let i = 0; i < nelem; ++i) {
    let p = i*4
    view.setUint8(0, buf.charCodeAt(p))
    view.setUint8(1, buf.charCodeAt(p + 1))
    view.setUint8(2, buf.charCodeAt(p + 2))
    view.setUint8(3, buf.charCodeAt(p + 3))
    outArray[i] = view.getFloat32(0,true)
  }

  return outArray
}

export function extract_pol(data: Array<Float32Array>, offset: number, step: number, nPols: number) {

  var nEpochs = data.length
  var nChans = data[0].length/nPols
  console.log(nEpochs,'nepochs',nChans, 'nchans')
  var outArray = new Array<Float32Array>()
  for (let i = 0; i < nChans; ++i) {
    outArray.push(new Float32Array(nEpochs))
  }
  for (let i = 0; i < nEpochs; ++i) {
    for (let j = 0; j < nChans; ++j) {
      outArray[j][i] = data[i][offset + j * step]
    }
  }
  console.log('xx out array shape',outArray.length,outArray[0].length)
  return outArray
}

export function get_xx(data: Array<Float32Array>, nPols: number) {
  var step = nPols == 4 ? 4 : 1
  var offset = 0
  return extract_pol(data, offset, step,nPols)
}

export function get_yy(data: Array<Float32Array>, nPols: number) {
  var step = nPols == 4 ? 4 : 1
  var offset = 1
  return extract_pol(data, offset, step,nPols)
}

export function get_stokes_I(xx: Array<Float32Array>, yy: Array<Float32Array>) {
  if (xx.length != yy.length) {
    throw ('Array dimensions mismatch')
  }

  var nChans = xx.length
  var nEpochs = xx[0].length
  var outArray = new Array<Float32Array>()

  for(let i=0;i<nChans;++i){
    outArray.push(new Float32Array(nEpochs))
  }

  for (let i = 0; i < nChans; ++i) {
    
    for (let j = 0; j < nEpochs; ++j) {
      outArray[i][j] = xx[i][j] + yy[i][j]
    }
  }

  return outArray
}

// function transposeArray(data: Array<Float32Array>, nChans: number){
//   var ntimes = data.length
//   for(let i=0;i<ntimes;++i){
//     for(let j=0;j<nChans;++j){
//       if(i>j) continue
//       let temp = data[i][j]
      
//     }
//   }
// }


