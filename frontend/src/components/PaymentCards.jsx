// The three sections of /pay. ConfirmCard owns the enable-rule for the Confirm button.
import { Alert, Button, Card, EyeToggle, Money, ReadOnlyField, Skeleton, Spinner, StatusBadge } from './ui.jsx'

export function PayerCard({ profile, account }) {
  const loading = profile.isPending || account.isPending
  return (
    <Card title="Payer information" hint="read-only">
      {loading ? (
        <div className="space-y-3">{[1, 2, 3, 4].map((i) => <Skeleton key={i} />)}</div>
      ) : (
        <>
          <ReadOnlyField label="Full name">{profile.data?.full_name}</ReadOnlyField>
          <ReadOnlyField label="Phone number">{profile.data?.phone}</ReadOnlyField>
          <ReadOnlyField label="Email">{profile.data?.email}</ReadOnlyField>
          <ReadOnlyField label="Available balance">
            {account.data ? <span className="inline-flex items-center gap-1"><Money value={account.data.balance} /><EyeToggle className="-my-1 -mr-2" /></span> : '—'}
          </ReadOnlyField>
          {(profile.error || account.error) && <div className="mt-2"><Alert>{(profile.error || account.error).message}</Alert></div>}
        </>
      )}
    </Card>
  )
}

export function TuitionCard({ mssv, onMssvChange, lookupEnabled, tuition, disabled }) {
  const notFound = tuition.error?.status === 404
  const data = lookupEnabled ? tuition.data : undefined
  const loading = lookupEnabled && tuition.isFetching && !data

  return (
    <Card title="Tuition details">
      <label className="block space-y-1">
        <span className="text-sm font-medium text-slate-700">Student ID (MSSV)</span>
        <div className="relative">
          <input
            value={mssv}
            onChange={(e) => onMssvChange(e.target.value.replace(/\s/g, '').toUpperCase())}
            disabled={disabled}
            maxLength={12}
            inputMode="numeric"
            autoComplete="off"
            placeholder="e.g. 52100001"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 pr-9 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:bg-slate-50"
          />
          {lookupEnabled && tuition.isFetching && <Spinner className="absolute right-3 top-3 h-4 w-4 text-blue-600" />}
        </div>
        <span className="text-xs text-slate-500">Type the 8-digit MSSV — it looks up automatically.</span>
      </label>

      <div className="mt-4 border-t border-slate-100 pt-3">
        {loading ? (
          <div className="space-y-3">{[1, 2, 3, 4].map((i) => <Skeleton key={i} />)}</div>
        ) : (
          <>
            <ReadOnlyField label="Student name">{data?.student_name}</ReadOnlyField>
            <ReadOnlyField label="Term">{data?.term}</ReadOnlyField>
            <ReadOnlyField label="Status">{data ? <StatusBadge status={data.status} /> : null}</ReadOnlyField>
            <ReadOnlyField label="Amount due">{data ? <Money value={data.amount} /> : null}</ReadOnlyField>
          </>
        )}
        {lookupEnabled && notFound && <div className="mt-3"><Alert>No tuition found for MSSV {mssv}.</Alert></div>}
        {lookupEnabled && tuition.error && !notFound && (
          <div className="mt-3"><Alert action={<Button variant="secondary" onClick={() => tuition.refetch()}>Retry</Button>}>{tuition.error.message}</Alert></div>
        )}
        {data?.status === 'PAID' && <div className="mt-3"><Alert kind="info">This tuition is already paid.</Alert></div>}
        {data?.status === 'RESERVED' && (
          <div className="mt-3"><Alert kind="warning">A payment for this tuition is in progress. If it is yours, resume it from Home.</Alert></div>
        )}
      </div>
    </Card>
  )
}

// Why the Confirm button is disabled (null = enabled). Shown directly above the button.
export function blockReason({ tuition, balance, agreed }) {
  if (!tuition) return 'Enter an MSSV that has tuition to pay.'
  if (tuition.status === 'PAID') return 'This tuition is already paid.'
  if (tuition.status !== 'UNPAID') return 'A payment for this tuition is already in progress.'
  if (balance == null) return 'Loading your balance…'
  if (Number(balance) < Number(tuition.amount)) return 'insufficient'
  if (!agreed) return 'Accept the terms & conditions to continue.'
  return null
}

export function ConfirmCard({ tuition, balance, agreed, onAgreedChange, onClear, onConfirm, submitting, submitError }) {
  // Only a tuition that can actually be paid feeds the summary.
  const amount = tuition?.status === 'UNPAID' ? Number(tuition.amount) : null
  const after = balance != null && amount != null ? Number(balance) - amount : null
  const reason = blockReason({ tuition, balance, agreed })

  return (
    <Card title="Confirm payment">
      <div className="max-w-md">
        <ReadOnlyField label="Available balance">{balance != null ? <Money value={balance} /> : null}</ReadOnlyField>
        <ReadOnlyField label="Tuition amount">{amount != null ? <span>− <Money value={amount} /></span> : null}</ReadOnlyField>
        <div className="mt-1 border-t border-slate-200 pt-1">
          <ReadOnlyField label="Balance after payment">
            {after != null ? <Money value={after} className={after < 0 ? 'text-red-600' : ''} /> : null}
          </ReadOnlyField>
        </div>
      </div>

      <label className="mt-4 flex items-start gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={agreed} onChange={(e) => onAgreedChange(e.target.checked)} className="mt-0.5 h-4 w-4 accent-blue-600" />
        <span>I agree to the terms &amp; conditions</span>
      </label>
      <details className="ml-6 mt-1 text-xs text-slate-500">
        <summary className="cursor-pointer select-none">Read the terms</summary>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          <li>The full tuition amount is paid in one transaction; partial payment is not possible.</li>
          <li>The payment is confirmed with a one-time code sent to your email, valid for 5 minutes.</li>
          <li>After it succeeds the payment cannot be reversed from this app.</li>
        </ul>
      </details>

      <div className="mt-4 space-y-3">
        {submitError && <Alert>{submitError}</Alert>}
        {!submitError && reason === 'insufficient' && (
          <Alert>Insufficient balance. You need <Money value={-after} /> more.</Alert>
        )}
        {!submitError && reason && reason !== 'insufficient' && tuition && <p className="text-sm text-slate-500">{reason}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClear} disabled={submitting}>Clear</Button>
          <Button onClick={onConfirm} disabled={reason !== null} loading={submitting}>Confirm transaction</Button>
        </div>
      </div>
    </Card>
  )
}
