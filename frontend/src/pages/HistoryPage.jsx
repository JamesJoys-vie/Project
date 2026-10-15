// All transactions (GET /transactions, newest first) with client-side MSSV / status filters.
import { useTransactions } from '../hooks/queries.js'
import HistoryTable from '../components/HistoryTable.jsx'
import { Alert, Button, Card } from '../components/ui.jsx'

export default function HistoryPage() {
  const txns = useTransactions()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-900">Transaction history</h1>
        <Button variant="secondary" onClick={() => txns.refetch()} loading={txns.isFetching && !txns.isPending}>Refresh</Button>
      </div>
      <Card>
        {txns.error ? (
          <Alert action={<Button variant="secondary" onClick={() => txns.refetch()}>Retry</Button>}>{txns.error.message}</Alert>
        ) : (
          <HistoryTable transactions={txns.data} loading={txns.isPending} />
        )}
      </Card>
    </div>
  )
}
