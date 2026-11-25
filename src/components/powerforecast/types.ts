/** 新能源功率预测标准（power_forecast_std）前端数据结构 */

/** 一个日前预测窗口：前一天 24h 实测 + 次日 24h NWP 预报，次日 24h 真值 / 预测 / 名义曲线基线 */
export interface PfCase {
  file: string
  station: string
  kind: 'wind' | 'solar' | string
  capacityMw: number
  weather: string
  startHour: number
  /** 前一天 24h 实测功率（MW） */
  history: number[]
  /** 第 h 项：前一天 h 时实测值，nwp_* 为次日 h 时 NWP 预报值 */
  channels: {
    wind_speed_ms: number[]
    irradiance_wm2: number[]
    temp_c: number[]
    humidity_pct: number[]
    pressure_hpa: number[]
    nwp_wind_ms: number[]
    nwp_irr_wm2: number[]
  }
  gt: number[] | null
  pred: number[] | null
  /** 基线：NWP + 名义功率曲线 */
  nominal?: number[] | null
  accuracy?: number
  nrmse?: number
  nmae?: number
  peakErrMw?: number
}

export interface PfBaseline {
  key: string
  name: string
  accuracy: number
  nrmse: number
}

export interface PfEvalVizData {
  lookback: number
  horizon: number
  /** 光伏考核时段 [起, 止]（含） */
  solarEvalHours: [number, number]
  evalHours: number
  baselines: PfBaseline[]
  cases: PfCase[]
  horizonCurve: { hour: number; nrmse: number; nmae: number; nominal: number; persistence: number }[]
  diurnalCurve: { hour: number; gt: number; pred: number }[]
  errorCdf: { mw: number; pct: number }[]
  history: { epoch: number; train_loss: number; val_loss: number; val_acc: number }[]
  bestEpoch?: number | null
}
