import { useEffect, useRef, useState } from 'react'
import { createChart, CrosshairMode } from 'lightweight-charts'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'
import { PriceBar } from '../api'
import type { InstitutionalBar, MarginBar } from '../api'
import { simpleMovingAverage } from '../ma'
import { applyCrosshairToOthers, crosshairTime, type SyncPane } from '../chartSync'
import { lotsValue, toLots, toPercent } from '../chipMath'

export interface ChartStackProps {
  bars: PriceBar[]
  institutional: InstitutionalBar[]
  margin: MarginBar[]
  showInstitutional: boolean
  showMargin: boolean
  maPeriods?: number[]   // 預設 [5, 20, 60]
}

const MA_COLORS = ['#f9a825', '#1e88e5', '#8e24aa', '#00897b']
const DEFAULT_MA_PERIODS = [5, 20, 60]

export default function ChartStack(props: ChartStackProps) {
  const {
    bars,
    institutional,
    margin,
    showInstitutional,
    showMargin,
    maPeriods = DEFAULT_MA_PERIODS,
  } = props

  const mainRef = useRef<HTMLDivElement>(null)
  const volumeRef = useRef<HTMLDivElement>(null)
  const instRef = useRef<HTMLDivElement>(null)
  const marginRef = useRef<HTMLDivElement>(null)

  const [hoverTime, setHoverTime] = useState<string | null>(null)

  useEffect(() => {
    // 過濾有效的 K 棒
    const validBars = bars.filter(
      (b) => b.open !== null && b.high !== null && b.low !== null && b.close !== null
    )

    if (validBars.length === 0) {
      return
    }

    if (!mainRef.current || !volumeRef.current) return
    if (showInstitutional && !instRef.current) return
    if (showMargin && !marginRef.current) return

    // 建立所有 pane 與 chart
    const panes: SyncPane[] = []
    const charts: IChartApi[] = []
    const syncingRef = { current: false }

    const common = {
      rightPriceScale: { minimumWidth: 72 },
      leftPriceScale: { visible: false },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: false, secondsVisible: false },
    }

    // 主圖
    const mainChart = createChart(mainRef.current, {
      width: mainRef.current.clientWidth,
      height: 360,
      ...common,
    })
    charts.push(mainChart)

    const candlestickSeries = mainChart.addCandlestickSeries({
      upColor: '#d32f2f',
      downColor: '#2e7d32',
      borderUpColor: '#d32f2f',
      borderDownColor: '#2e7d32',
      wickUpColor: '#d32f2f',
      wickDownColor: '#2e7d32',
    })

    candlestickSeries.setData(
      validBars.map((bar) => ({
        time: bar.time,
        open: bar.open!,
        high: bar.high!,
        low: bar.low!,
        close: bar.close!,
      }))
    )

    const maSeriesRefs: ISeriesApi<'Line'>[] = []
    maPeriods.forEach((period, idx) => {
      const maPoints = simpleMovingAverage(validBars, period)
      if (maPoints.length > 0) {
        const lineSeries = mainChart.addLineSeries({
          color: MA_COLORS[idx % MA_COLORS.length],
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        lineSeries.setData(maPoints)
        maSeriesRefs.push(lineSeries)
      }
    })

    const valueByTimeMain = new Map(validBars.map((bar) => [bar.time, bar.close!]))

    panes.push({
      id: 'main',
      chart: mainChart,
      series: candlestickSeries,
      valueByTime: valueByTimeMain,
    })

    // 成交量圖
    const volumeChart = createChart(volumeRef.current, {
      width: volumeRef.current.clientWidth,
      height: 110,
      ...common,
    })
    charts.push(volumeChart)

    const volumeSeries = volumeChart.addHistogramSeries({
      priceFormat: { type: 'volume' },
    })

    volumeSeries.setData(
      validBars.map((bar) => ({
        time: bar.time,
        value: lotsValue(bar.volume),
        color: bar.close! >= bar.open! ? '#d32f2f' : '#2e7d32',
      }))
    )

    const valueByTimeVolume = new Map(validBars.map((bar) => [bar.time, lotsValue(bar.volume)]))

    panes.push({
      id: 'volume',
      chart: volumeChart,
      series: volumeSeries,
      valueByTime: valueByTimeVolume,
    })

    // 法人圖（如果顯示）
    if (showInstitutional && instRef.current) {
      const instChart = createChart(instRef.current, {
        width: instRef.current.clientWidth,
        height: 110,
        ...common,
      })
      charts.push(instChart)

      const instSeries = instChart.addHistogramSeries({
        priceFormat: { type: 'volume' },
      })

      instSeries.setData(
        institutional.map((bar) => ({
          time: bar.time,
          value: lotsValue(bar.total_net),
          color: bar.total_net >= 0 ? '#d32f2f' : '#2e7d32',
        }))
      )

      const valueByTimeInst = new Map(
        institutional.map((bar) => [bar.time, lotsValue(bar.total_net)])
      )

      panes.push({
        id: 'institutional',
        chart: instChart,
        series: instSeries,
        valueByTime: valueByTimeInst,
      })
    }

    // 融資券圖（如果顯示）
    if (showMargin && marginRef.current) {
      const marginChart = createChart(marginRef.current, {
        width: marginRef.current.clientWidth,
        height: 110,
        ...common,
      })
      charts.push(marginChart)

      const marginSeriesBalance = marginChart.addLineSeries({
        color: '#f57c00',
        lineWidth: 1,
      })

      marginSeriesBalance.setData(
        margin.map((bar) => ({
          time: bar.time,
          value: lotsValue(bar.margin_balance),
        }))
      )

      const marginSeriesShort = marginChart.addLineSeries({
        color: '#1e88e5',
        lineWidth: 1,
      })

      marginSeriesShort.setData(
        margin.map((bar) => ({
          time: bar.time,
          value: lotsValue(bar.short_balance),
        }))
      )

      const valueByTimeMargin = new Map(margin.map((bar) => [bar.time, lotsValue(bar.margin_balance)]))

      panes.push({
        id: 'margin',
        chart: marginChart,
        series: marginSeriesBalance,
        valueByTime: valueByTimeMargin,
      })
    }

    // 只有最後一個 pane 顯示時間軸
    for (let i = 0; i < panes.length; i++) {
      if (i < panes.length - 1) {
        (panes[i].chart as any).applyOptions({ timeScale: { visible: false } })
      }
    }

    // 訂閱時間軸同步
    for (const p of panes) {
      const rawChart = p.chart as any
      rawChart.timeScale().subscribeVisibleLogicalRangeChange(() => {
        if (syncingRef.current) return
        syncingRef.current = true
        const range = rawChart.timeScale().getVisibleLogicalRange()
        if (range) {
          for (const q of panes) {
            if (q !== p) {
              const qRaw = q.chart as any
              qRaw.timeScale().setVisibleLogicalRange(range)
            }
          }
        }
        syncingRef.current = false
      })

      // 十字線同步 + 讀數面板
      rawChart.subscribeCrosshairMove((param: any) => {
        const t = crosshairTime(param)
        applyCrosshairToOthers(panes, p.id, t)
        setHoverTime(t)
      })
    }

    // 適應內容
    (panes[0].chart as any).timeScale().fitContent()

    // ResizeObserver 監看寬度變化
    const resizeObserver = new ResizeObserver(() => {
      const widths = [
        mainRef.current?.clientWidth || 0,
        volumeRef.current?.clientWidth || 0,
        showInstitutional ? (instRef.current?.clientWidth || 0) : 0,
        showMargin ? (marginRef.current?.clientWidth || 0) : 0,
      ]

      for (let i = 0; i < panes.length; i++) {
        (panes[i].chart as any).applyOptions({ width: widths[i] || 0 })
      }
    })

    if (mainRef.current) resizeObserver.observe(mainRef.current)
    if (volumeRef.current) resizeObserver.observe(volumeRef.current)
    if (showInstitutional && instRef.current) resizeObserver.observe(instRef.current)
    if (showMargin && marginRef.current) resizeObserver.observe(marginRef.current)

    return () => {
      resizeObserver.disconnect()
      for (const chart of charts) {
        chart.remove()
      }
    }
  }, [bars, institutional, margin, showInstitutional, showMargin, maPeriods])

  // 找顯示的日期數據
  const displayTime = hoverTime && bars.find((b) => b.time === hoverTime) ? hoverTime : bars[bars.length - 1]?.time
  const displayBar = displayTime ? bars.find((b) => b.time === displayTime) : null
  const displayInst = displayTime ? institutional.find((b) => b.time === displayTime) : null
  const displayMargin = displayTime ? margin.find((b) => b.time === displayTime) : null

  return (
    <div className="chart-stack">
      <div className="chart-readout" data-testid="chart-readout">
        <div className="readout-item">
          <span className="readout-label">日期</span>
          <span className="readout-value" data-testid="readout-date">
            {displayTime || '—'}
          </span>
        </div>
        <div className="readout-item">
          <span className="readout-label">開高低收</span>
          <span className="readout-value" data-testid="readout-ohlc">
            {displayBar
              ? `開 ${displayBar.open?.toFixed(2)} 高 ${displayBar.high?.toFixed(2)} 低 ${displayBar.low?.toFixed(2)} 收 ${displayBar.close?.toFixed(2)}`
              : '—'}
          </span>
        </div>
        <div className="readout-item">
          <span className="readout-label">漲跌</span>
          <span
            className={`readout-value ${displayBar && displayBar.change ? (displayBar.change >= 0 ? 'up' : 'down') : ''}`}
            data-testid="readout-change"
          >
            {displayBar && displayBar.change !== null
              ? `${displayBar.change >= 0 ? '+' : ''}${displayBar.change.toFixed(2)}`
              : '—'}
          </span>
        </div>
        <div className="readout-item">
          <span className="readout-label">成交量</span>
          <span className="readout-value" data-testid="readout-volume">
            {displayBar ? toLots(displayBar.volume) : '—'}
          </span>
        </div>
        <div className="readout-item">
          <span className="readout-label">外資</span>
          <span
            className={`readout-value ${displayInst && displayInst.foreign_net ? (displayInst.foreign_net >= 0 ? 'up' : 'down') : ''}`}
            data-testid="readout-foreign"
          >
            {displayInst ? toLots(displayInst.foreign_net) : '—'}
          </span>
        </div>
        <div className="readout-item">
          <span className="readout-label">投信</span>
          <span className="readout-value" data-testid="readout-trust">
            {displayInst ? toLots(displayInst.trust_net) : '—'}
          </span>
        </div>
        <div className="readout-item">
          <span className="readout-label">自營</span>
          <span className="readout-value" data-testid="readout-dealer">
            {displayInst ? toLots(displayInst.dealer_net) : '—'}
          </span>
        </div>
        <div className="readout-item">
          <span className="readout-label">融資餘額</span>
          <span className="readout-value" data-testid="readout-margin">
            {displayMargin ? toLots(displayMargin.margin_balance) : '—'}
          </span>
        </div>
        <div className="readout-item">
          <span className="readout-label">融券餘額</span>
          <span className="readout-value" data-testid="readout-short">
            {displayMargin ? toLots(displayMargin.short_balance) : '—'}
          </span>
        </div>
      </div>

      <div className="chart-pane chart-pane-main">
        <div className="chart-pane-title">K 線</div>
        <div ref={mainRef} style={{ width: '100%', height: '100%' }} />
      </div>

      <div className="chart-pane">
        <div className="chart-pane-title">成交量（張）</div>
        <div ref={volumeRef} style={{ width: '100%', height: '100%' }} />
      </div>

      {showInstitutional && (
        <div className="chart-pane">
          <div className="chart-pane-title">三大法人買賣超（張）</div>
          <div ref={instRef} style={{ width: '100%', height: '100%' }} />
        </div>
      )}

      {showMargin && (
        <div className="chart-pane">
          <div className="chart-pane-title">融資融券餘額（張）</div>
          <div ref={marginRef} style={{ width: '100%', height: '100%' }} />
        </div>
      )}
    </div>
  )
}
