import { useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'
import { PriceBar } from '../api'
import { simpleMovingAverage } from '../ma'

export interface CandleChartProps {
  bars: PriceBar[]
  maPeriods?: number[]
  height?: number
  volumeHeight?: number
}

const MA_COLORS = ['#f9a825', '#1e88e5', '#8e24aa', '#00897b']

export default function CandleChart(props: CandleChartProps) {
  const {
    bars,
    maPeriods = [5, 20, 60],
    height = 400,
    volumeHeight = 120,
  } = props

  const containerRef = useRef<HTMLDivElement>(null)
  const volumeContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const volumeChartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const lineSeriesRefsRef = useRef<ISeriesApi<'Line'>[]>([])
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const syncingRef = useRef(false)

  useEffect(() => {
    if (!containerRef.current || !volumeContainerRef.current) return

    // 建立主圖表
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    })
    chartRef.current = chart

    // 建立成交量圖表
    const volumeChart = createChart(volumeContainerRef.current, {
      width: volumeContainerRef.current.clientWidth,
      height: volumeHeight,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    })
    volumeChartRef.current = volumeChart

    // 建立 series（只建一次，後續只更新資料）
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#d32f2f',
      downColor: '#2e7d32',
      borderUpColor: '#d32f2f',
      borderDownColor: '#2e7d32',
      wickUpColor: '#d32f2f',
      wickDownColor: '#2e7d32',
    })
    candlestickSeriesRef.current = candlestickSeries

    const volumeSeries = volumeChart.addHistogramSeries({
      priceFormat: { type: 'volume' },
    })
    volumeSeriesRef.current = volumeSeries

    // 同步時間軸
    const mainTimeScale = chart.timeScale()
    const volumeTimeScale = volumeChart.timeScale()

    mainTimeScale.subscribeVisibleLogicalRangeChange(() => {
      if (syncingRef.current) return
      syncingRef.current = true
      const range = mainTimeScale.getVisibleLogicalRange()
      if (range) {
        volumeTimeScale.setVisibleLogicalRange(range)
      }
      syncingRef.current = false
    })

    volumeTimeScale.subscribeVisibleLogicalRangeChange(() => {
      if (syncingRef.current) return
      syncingRef.current = true
      const range = volumeTimeScale.getVisibleLogicalRange()
      if (range) {
        mainTimeScale.setVisibleLogicalRange(range)
      }
      syncingRef.current = false
    })

    // 監看容器寬度
    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current && volumeContainerRef.current) {
        const width = containerRef.current.clientWidth
        chart.applyOptions({ width })
        volumeChart.applyOptions({ width })
      }
    })
    resizeObserver.observe(containerRef.current)
    resizeObserver.observe(volumeContainerRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      volumeChart.remove()
    }
  }, [height, volumeHeight])

  // 更新資料
  useEffect(() => {
    if (!chartRef.current || !volumeChartRef.current) return
    if (!candlestickSeriesRef.current || !volumeSeriesRef.current) return

    // 過濾掉有 null 的 K 棒
    const validBars = bars.filter(
      (bar) =>
        bar.open !== null &&
        bar.high !== null &&
        bar.low !== null &&
        bar.close !== null
    )

    if (validBars.length === 0) {
      return
    }

    const chart = chartRef.current
    const candlestickSeries = candlestickSeriesRef.current
    const volumeSeries = volumeSeriesRef.current

    // 更新 K 線資料
    candlestickSeries.setData(
      validBars.map((bar) => ({
        time: bar.time,
        open: bar.open!,
        high: bar.high!,
        low: bar.low!,
        close: bar.close!,
      }))
    )

    // 移除舊的均線 series 並重新建立
    const lineSeriesRefs = lineSeriesRefsRef.current
    lineSeriesRefs.forEach((series) => {
      chart.removeSeries(series)
    })
    lineSeriesRefs.length = 0

    // 設定新的均線
    maPeriods.forEach((period, idx) => {
      const maPoints = simpleMovingAverage(validBars, period)
      if (maPoints.length > 0) {
        const lineSeries = chart.addLineSeries({
          color: MA_COLORS[idx % MA_COLORS.length],
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        lineSeries.setData(maPoints)
        lineSeriesRefs.push(lineSeries)
      }
    })

    // 更新成交量資料
    volumeSeries.setData(
      validBars.map((bar) => ({
        time: bar.time,
        value: bar.volume,
        color: bar.close! >= bar.open! ? '#d32f2f' : '#2e7d32',
      }))
    )

    // 自動調整圖表
    chart.timeScale().fitContent()
    chartRef.current.timeScale().fitContent()
  }, [bars, maPeriods])

  return (
    <div>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      <div
        ref={volumeContainerRef}
        style={{ width: '100%', marginTop: '10px' }}
      />
    </div>
  )
}
