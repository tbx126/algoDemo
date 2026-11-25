export interface PfCase {
  file: string
  station: string
  kind: 'wind' | 'solar' | string
  weather: string
  startHour: number
  hours48: string[]
  history: number[]
  channels: {
    wind_speed_ms: number[]
    irradiance_wm2: number[]
    nwp_wind_ms: number[]
    nwp_irr_wm2: number[]
    temp_c: number[]
  }
  gt: number[] | null
  pred: number[] | null
  accuracy?: number
  nrmse?: number
  nmae?: number
  peakErrMw?: number
}

export interface PfEvalVizData {
  capacityMw: number
  lookback: number
  horizon: number
  cases: PfCase[]
  horizonCurve: { hour: number; nrmse: number; nmae: number }[]
  diurnalCurve: { hour: number; gt: number; pred: number }[]
  errorCdf: { mw: number; pct: number }[]
  history: { epoch: number; train_loss: number; val_loss: number; val_acc: number }[]
}
