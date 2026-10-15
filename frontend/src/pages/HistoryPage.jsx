// TODO: table of GET /api/transactions (date, MSSV, amount, status).
import { Link } from 'react-router-dom'

export default function HistoryPage() {
  return (
    <main className="max-w-3xl mx-auto p-6 space-y-4">
      <Link to="/pay" className="text-blue-600 text-sm">&larr; Back</Link>
      <h1 className="text-2xl font-semibold">Transaction history</h1>
      <p className="text-slate-500">Placeholder</p>
    </main>
  )
}
