import { useEffect, useState } from 'react'
import { fetchEtlSummary, fetchEtlJobs } from '../api'
import type { EtlJobSummaryItem, EtlJobRun } from '../api'

export default function EtlStatusPage() {
  const [summary, setSummary] = useState<EtlJobSummaryItem[] | null>(null)
  const [jobs, setJobs] = useState<EtlJobRun[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  const loadData = async () => {
    try {
      setError(null)
      const [summaryData, jobsData] = await Promise.all([
        fetchEtlSummary(),
        fetchEtlJobs(50),
      ])
      setSummary(summaryData.items)
      setJobs(jobsData.items)
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        setError(err)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 30000)
    return () => clearInterval(interval)
  }, [])

  const statusLabel = (status: string) => {
    switch (status) {
      case 'success':
        return <span className={'status status-success'}>成功</span>
      case 'failed':
        return <span className={'status status-failed'}>失敗</span>
      case 'running':
        return <span className={'status status-running'}>執行中</span>
      case 'skipped':
        return <span className={'status status-skipped'}>略過</span>
      default:
        return <span>{status}</span>
    }
  }

  const formatTime = (isoString: string) => {
    const date = new Date(isoString)
    return date.toLocaleString('zh-TW', {
      timeZone: 'Asia/Taipei',
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const getDurationDisplay = (start: string, end: string | null) => {
    if (!end) return '進行中'
    const startTime = new Date(start).getTime()
    const endTime = new Date(end).getTime()
    const seconds = Math.round((endTime - startTime) / 1000)
    return `${seconds}s`
  }

  const truncateError = (error: string | null) => {
    if (!error) return ''
    if (error.length > 80) {
      return (
        <span title={error}>{error.substring(0, 80)}…</span>
      )
    }
    return error
  }

  if (loading) {
    return <p role="status">載入中…</p>
  }

  if (error) {
    return <p role="alert">載入失敗：{error.message}</p>
  }

  return (
    <div>
      <button onClick={loadData}>立即重新整理</button>

      <h2>各項工作狀態</h2>
      {summary && summary.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>工作</th>
              <th>最後狀態</th>
              <th>目標</th>
              <th>筆數</th>
              <th>開始時間</th>
              <th>耗時</th>
              <th>近 7 天失敗次數</th>
            </tr>
          </thead>
          <tbody>
            {summary.map((item) => (
              <tr key={item.job_name}>
                <td>{item.job_name}</td>
                <td>{statusLabel(item.last_status)}</td>
                <td>
                  {item.last_target_date || item.last_target_key || '—'}
                </td>
                <td>{item.last_rows}</td>
                <td>{formatTime(item.last_started_at)}</td>
                <td>
                  {getDurationDisplay(
                    item.last_started_at,
                    item.last_finished_at
                  )}
                </td>
                <td>{item.failed_last_7_days}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>無任何工作紀錄</p>
      )}

      <h2>最近執行紀錄</h2>
      {jobs && jobs.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>時間</th>
              <th>工作</th>
              <th>目標</th>
              <th>狀態</th>
              <th>筆數</th>
              <th>耗時</th>
              <th>錯誤訊息</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((item) => (
              <tr key={item.job_id}>
                <td>{formatTime(item.started_at)}</td>
                <td>{item.job_name}</td>
                <td>
                  {item.target_date || item.target_key || '—'}
                </td>
                <td>{statusLabel(item.status)}</td>
                <td>{item.rows}</td>
                <td>
                  {getDurationDisplay(item.started_at, item.finished_at)}
                </td>
                <td>{truncateError(item.error)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>無任何執行紀錄</p>
      )}
    </div>
  )
}
