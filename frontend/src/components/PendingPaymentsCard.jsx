// PENDING_OTP transactions with a live countdown, Resume (reopens the OTP modal on /pay) and Cancel.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cancelTransaction } from '../api/client.js'
import { keys } from '../hooks/queries.js'
import { useSecondsLeft } from '../hooks/useTimers.js'
import { formatClock, formatDateTime } from '../utils/format.js'
import { Alert, Button, Card, Money } from './ui.jsx'

function PendingRow({ txn, fetchedAt }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  // otp_expires_in is relative to when the list was fetched.
  const [deadline] = useState(() => fetchedAt + (txn.otp_expires_in ?? 0) * 1000)
  const left = useSecondsLeft(deadline)
  const cancel = useMutation({
    mutationFn: () => cancelTransaction(txn.id),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: keys.transactions })
      queryClient.invalidateQueries({ queryKey: keys.account })
    },
  })

  const onCancel = () => {
    if (window.confirm(`Cancel the payment for MSSV ${txn.student_id}?`)) cancel.mutate()
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div>
        <p className="font-medium text-slate-800">{txn.student_id}</p>
        <p className="text-xs text-slate-500">
          Started {formatDateTime(txn.created_at).slice(-5)} · {left > 0 ? `expires in ${formatClock(left)}` : 'expired'}
        </p>
        {cancel.error && <p className="mt-1 text-xs text-red-600">{cancel.error.message}</p>}
      </div>
      <div className="flex items-center gap-3">
        <Money value={txn.amount} className="font-medium" />
        <Button variant="secondary" onClick={onCancel} loading={cancel.isPending}>Cancel</Button>
        <Button onClick={() => navigate(`/pay?resume=${txn.id}`)} disabled={left === 0}>Resume</Button>
      </div>
    </li>
  )
}

export default function PendingPaymentsCard({ transactions, fetchedAt }) {
  const pending = (transactions || []).filter((t) => t.status === 'PENDING_OTP')
  if (pending.length === 0) return null
  return (
    <Card title={`Waiting for OTP · ${pending.length}`} hint="Finish or cancel before it expires" className="border-amber-300">
      <Alert kind="warning">Lost the email? Resume and press “Resend code”.</Alert>
      <ul className="divide-y divide-slate-100">
        {pending.map((t) => <PendingRow key={t.id} txn={t} fetchedAt={fetchedAt} />)}
      </ul>
    </Card>
  )
}
