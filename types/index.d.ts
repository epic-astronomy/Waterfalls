export type WatchStatus = 'watching' | 'watched'

export interface WatchListItem{
  author: String,
  dec_deg: number,
  event_time: Date,
  event_type: String,
  id: number,
  patch_type: number,
  ra_deg: number,
  reason: String,
  source: String,
  t_start: Date,
  t_end: Date,
  voevent: String,
  watch_mode: WatchStatus,
  watch_status: String
}

export interface WatchList{
  data: WatchListItem[],
  count: number
}

export interface ImgSessionItem {
  start_time: Date,
  end_time: Date,
  session_id: String,
  chan0: number,
  n_chan: number,
  n_pol: number,
  chan_bw_hz: number,
  int_time: number
}

export interface ImgSessions{
  data: ImgSessionItem[],
  count: number
}

export interface SessionQuery{
  tStart: String,
  tEnd: String,
  sourceName: String
}

export interface SpecgmQuery{
  start_time: String,
  end_time: String,
  source_name: String,
  session_id: String,
  pixel_positions: String,
  n_chan: number,
  n_pols: number,
  chan_bw_hz: number,
  start_chan: number,
}

export interface SpecgmData{
  pixel_values: string,
  img_time: string
}

export interface DailyDigestSrc{
  source_name: string,
  chan0: number,
  chan_bw_hz: number
}

export interface DailyDigestSrcConfig{
  source_name: string,
  chan0: int[],
  chan_bw_hz: int[]
}

export interface DailyDigestData{
  img_time: string,
  stokes_i: number[],
  stokes_v: number[],
  cfreq: number
}
export interface DailyDigestTraceData{
  img_time: string[],
  stokes_I: Array<Float32Array>,
  stokes_V: Array<Float32Array>,
  freqs: number[]
}

export interface DailyDigestStats{
  cfreq: number,
  count: number
}

export interface DailyDigestResp{
  stats: DailyDigestStats[],
  data: DailyDigestData[]
}