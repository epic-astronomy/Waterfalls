// HEALPix in RING order (Górski et al. 2005), as healpy's ang2pix and pix2ang
// with nest=False: the grid the all-sky monitors track the sky on. theta is
// the colatitude and phi the longitude, in radians.

const HALF_PI = Math.PI / 2

function imod(a: number, m: number) {
  const r = a % m
  return r < 0 ? r + m : r
}

export function npix(nside: number) {
  return 12 * nside * nside
}

export const ang2pix = (nside: number, theta: number, phi: number) => ang2pixZ(nside, Math.cos(theta), phi)

// from z = cos(theta) = sin(dec), which saves the trigonometry when drawing a map
export function ang2pixZ(nside: number, z: number, phi: number) {
  const za = Math.abs(z)
  let tt = (phi / HALF_PI) % 4
  if (tt < 0) tt += 4
  if (za <= 2 / 3) {
    // equatorial belt
    const t1 = nside * (0.5 + tt)
    const t2 = nside * z * 0.75
    const jp = Math.floor(t1 - t2)
    const jm = Math.floor(t1 + t2)
    const ir = nside + 1 + jp - jm
    const kshift = 1 - (ir & 1)
    const ip = imod(Math.floor((jp + jm - nside + kshift + 1) / 2), 4 * nside)
    return 2 * nside * (nside - 1) + (ir - 1) * 4 * nside + ip
  }
  // polar caps
  const tp = tt - Math.floor(tt)
  const tmp = nside * Math.sqrt(3 * (1 - za))
  const jp = Math.floor(tp * tmp)
  const jm = Math.floor((1 - tp) * tmp)
  const ir = jp + jm + 1
  const ip = imod(Math.floor(tt * ir), 4 * ir)
  return z > 0 ? 2 * ir * (ir - 1) + ip : 12 * nside * nside - 2 * ir * (ir + 1) + ip
}

// centre of a pixel: [theta, phi]
export function pix2ang(nside: number, pix: number): [number, number] {
  const ncap = 2 * nside * (nside - 1)
  const np = 12 * nside * nside
  let z: number, phi: number
  if (pix < ncap) {
    const ir = (1 + Math.floor(Math.sqrt(1 + 2 * pix))) >> 1
    const iphi = pix + 1 - 2 * ir * (ir - 1)
    z = 1 - ir * ir * 4 / np
    phi = (iphi - 0.5) * HALF_PI / ir
  } else if (pix < np - ncap) {
    const ip = pix - ncap
    const ir = Math.floor(ip / (4 * nside)) + nside
    const iphi = ip % (4 * nside) + 1
    const fodd = ((ir + nside) & 1) ? 1 : 0.5
    z = (2 * nside - ir) * 2 / (3 * nside)
    phi = (iphi - fodd) * HALF_PI / nside
  } else {
    const ip = np - pix
    const ir = (1 + Math.floor(Math.sqrt(2 * ip - 1))) >> 1
    const iphi = 4 * ir + 1 - (ip - 2 * ir * (ir - 1))
    z = -1 + ir * ir * 4 / np
    phi = (iphi - 0.5) * HALF_PI / ir
  }
  return [Math.acos(z), phi]
}

// pixel of a sky position in degrees, and the centre of a pixel in degrees
export const radec2pix = (nside: number, ra: number, dec: number) =>
  ang2pix(nside, (90 - dec) * Math.PI / 180, ra * Math.PI / 180)

export function pix2radec(nside: number, pix: number): [number, number] {
  const [th, ph] = pix2ang(nside, pix)
  return [ph * 180 / Math.PI, 90 - th * 180 / Math.PI]
}

// mean pixel size in degrees
export const pixDeg = (nside: number) => Math.sqrt(4 * Math.PI / npix(nside)) * 180 / Math.PI
