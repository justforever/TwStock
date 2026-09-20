import type { IChartApi, ISeriesApi, SeriesType, Time } from 'lightweight-charts'

/** 一個可被同步的 pane。chart 只用到兩個方法，方便測試時傳假物件。 */
export interface SyncPane {
  id: string
  chart: Pick<IChartApi, 'setCrosshairPosition' | 'clearCrosshairPosition'>
  series: ISeriesApi<SeriesType>
  /** 這個 pane 在每個日期的代表值，決定十字線的垂直位置（主圖用收盤、成交量用量…） */
  valueByTime: Map<string, number>
}

/**
 * 把來源 pane 的十字線時間套到其他所有 pane。
 * time 為 null（滑鼠移出圖表或不在資料範圍內）時，其他 pane 一律清掉十字線。
 */
export function applyCrosshairToOthers(
  panes: SyncPane[],
  sourceId: string,
  time: string | null
): void {
  for (const pane of panes) {
    if (pane.id === sourceId) continue
    if (time === null) {
      pane.chart.clearCrosshairPosition()
      continue
    }
    const value = pane.valueByTime.get(time)
    if (value === undefined) {
      pane.chart.clearCrosshairPosition()
      continue
    }
    pane.chart.setCrosshairPosition(value, time as Time, pane.series)
  }
}

/** 把 lightweight-charts 的 crosshair 事件參數轉成 'YYYY-MM-DD' 或 null。 */
export function crosshairTime(param: { time?: unknown }): string | null {
  const t = param.time
  return typeof t === 'string' && t.length === 10 ? t : null
}

/** 用日期字串在一組時間序列裡找索引；找不到回 -1。 */
export function indexOfTime(times: string[], time: string): number {
  return times.indexOf(time)
}
