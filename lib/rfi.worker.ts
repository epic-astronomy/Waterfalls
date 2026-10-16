// Runs the RFI flagger off the main thread, so the page stays responsive
import { rfiMask } from './rfi'

self.onmessage = (e: MessageEvent<{ id: number, channels: Float32Array[], dt: number }>) => {
  const { id, channels, dt } = e.data
  const t0 = performance.now()
  const mask = rfiMask(channels, dt)
  ;(self as unknown as Worker).postMessage({ id, mask, ms: performance.now() - t0 }, mask.map(m => m.buffer))
}
