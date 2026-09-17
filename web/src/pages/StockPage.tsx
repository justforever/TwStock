import { useParams } from 'react-router-dom'

export default function StockPage() {
  const { stockId } = useParams<{ stockId: string }>()

  return (
    <div>
      <h1>股票 {stockId}</h1>
      <p>個股頁（K 線、籌碼）將於 M1 實作。</p>
    </div>
  )
}
