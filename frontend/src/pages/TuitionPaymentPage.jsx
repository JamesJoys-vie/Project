// /pay: Details (payer, tuition lookup, confirm) -> OTP modal -> Result (replaces the form, same route).
// `?resume=<txnId>` (from Home's "Waiting for OTP" card) reopens the OTP modal for a PENDING_OTP transaction.
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getTransaction, getTuition, initiateTransaction } from '../api/client.js'
import { keys, useAccount, useProfile } from '../hooks/queries.js'
import { useDebounce } from '../hooks/useTimers.js'
import { newIdempotencyKey } from '../utils/format.js'
import { ConfirmCard, PayerCard, TuitionCard } from '../components/PaymentCards.jsx'
import OtpModal from '../components/OtpModal.jsx'
import ResultCard from '../components/ResultCard.jsx'
import { Alert, Stepper } from '../components/ui.jsx'

const MIN_MSSV = 8

export default function TuitionPaymentPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const profile = useProfile()
  const account = useAccount()

  const [mssv, setMssv] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [phase, setPhase] = useState('details') // details | otp | result
  const [pending, setPending] = useState(null) // { txn, tuition, expiresIn, cooldown }
  const [outcome, setOutcome] = useState(null) // { result, tuition }
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [notice, setNotice] = useState(null)
  // One Idempotency-Key per payment attempt: reused when the same attempt is retried (e.g. network error),
  // replaced once the attempt is over or the MSSV changes.
  const attempt = useRef(null) // { key, mssv }

  const debounced = useDebounce(mssv, 400)
  const lookupEnabled = mssv.length >= MIN_MSSV && debounced === mssv
  const tuition = useQuery({
    queryKey: ['tuition', debounced],
    queryFn: () => getTuition(debounced),
    enabled: lookupEnabled,
    staleTime: 0,
  })
  const currentTuition = lookupEnabled ? tuition.data : undefined

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: keys.account })
    queryClient.invalidateQueries({ queryKey: keys.transactions })
    queryClient.invalidateQueries({ queryKey: ['tuition'] })
  }

  // Resume a PENDING_OTP transaction (or show how it ended) when arriving with ?resume=<id>.
  const resumeId = searchParams.get('resume')
  const resumed = useRef(null)
  useEffect(() => {
    if (!resumeId || resumed.current === resumeId) return
    resumed.current = resumeId
    setSearchParams({}, { replace: true })
    ;(async () => {
      try {
        const txn = await getTransaction(resumeId)
        const info = await getTuition(txn.student_id).catch(() => null)
        setMssv(txn.student_id)
        if (txn.status === 'PENDING_OTP') {
          setPending({ txn, tuition: info, expiresIn: txn.otp_expires_in ?? 0, cooldown: 0 })
          setPhase('otp')
        } else {
          setOutcome({ result: { transaction: txn, balance_after: null }, tuition: info })
          setPhase('result')
        }
      } catch (e) {
        setNotice({ kind: 'error', text: e.status === 404 ? 'That transaction was not found.' : e.message })
      }
    })()
  }, [resumeId, setSearchParams])

  const onMssvChange = (value) => {
    setMssv(value)
    setSubmitError(null)
    setNotice(null)
  }

  const resetForm = () => {
    setMssv(''); setAgreed(false); setSubmitError(null); setNotice(null)
    setPending(null); setOutcome(null); setPhase('details')
    attempt.current = null
  }

  const onConfirm = async () => {
    const t = currentTuition
    if (!t) return
    if (attempt.current?.mssv !== t.student_id) attempt.current = { key: newIdempotencyKey(), mssv: t.student_id }
    setSubmitting(true); setSubmitError(null); setNotice(null)
    try {
      const txn = await initiateTransaction(t.student_id, attempt.current.key)
      queryClient.invalidateQueries({ queryKey: keys.transactions })
      if (txn.status === 'PENDING_OTP') {
        setPending({ txn, tuition: t, expiresIn: txn.otp_expires_in ?? 300, cooldown: 30 })
        setPhase('otp')
      } else {
        // Same key replayed for an attempt that already ended.
        attempt.current = null
        setOutcome({ result: { transaction: txn, balance_after: null }, tuition: t })
        setPhase('result')
      }
    } catch (e) {
      if (e.status === 409 || e.status === 422 || e.status === 404) {
        attempt.current = null // the server rejected this attempt; a later one is a new request
        refreshAll()
      }
      setSubmitError(e.status === 429 ? `Too many requests. Try again in ${e.retryAfter || 60} seconds.` : e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const onResult = (result) => {
    attempt.current = null
    setOutcome({ result, tuition: pending?.tuition })
    setPending(null)
    setPhase('result')
    refreshAll()
  }

  const onCancelled = () => {
    attempt.current = null
    setPending(null)
    setPhase('details')
    setNotice({ kind: 'info', text: 'Payment cancelled. No money was taken from your account.' })
    refreshAll()
  }

  const tryAgain = () => {
    setOutcome(null); setSubmitError(null); setNotice(null); setPhase('details')
    attempt.current = null
    refreshAll()
  }

  const status = outcome?.result.transaction.status
  const resultButtons = status === 'SUCCESS'
    ? { secondary: { label: 'Back to home', onClick: () => navigate('/home') }, primary: { label: 'New payment', onClick: resetForm } }
    : status === 'PROCESSING' || status === 'PENDING_OTP'
      ? { secondary: { label: 'View history', onClick: () => navigate('/history') }, primary: { label: 'New payment', onClick: resetForm } }
      : { secondary: { label: 'Back to form', onClick: resetForm }, primary: { label: 'Try again', onClick: tryAgain } }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-slate-900">Tuition payment</h1>
        <Stepper current={phase === 'details' ? 1 : phase === 'otp' ? 2 : 3} />
      </div>

      {phase === 'result' && outcome ? (
        <ResultCard result={outcome.result} tuition={outcome.tuition} {...resultButtons} />
      ) : (
        <>
          {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}
          <div className="grid gap-4 md:grid-cols-2">
            <PayerCard profile={profile} account={account} />
            <TuitionCard
              mssv={mssv}
              onMssvChange={onMssvChange}
              lookupEnabled={lookupEnabled}
              tuition={tuition}
              disabled={submitting || phase === 'otp'}
            />
          </div>
          <ConfirmCard
            tuition={currentTuition}
            balance={account.data?.balance}
            agreed={agreed}
            onAgreedChange={setAgreed}
            onClear={resetForm}
            onConfirm={onConfirm}
            submitting={submitting}
            submitError={submitError}
          />
        </>
      )}

      {phase === 'otp' && pending && (
        <OtpModal
          txn={pending.txn}
          tuition={pending.tuition}
          email={profile.data?.email}
          initialExpiresIn={pending.expiresIn}
          initialCooldown={pending.cooldown}
          onResult={onResult}
          onCancelled={onCancelled}
        />
      )}
    </div>
  )
}
