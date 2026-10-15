// OTP step: 6-box input, expiry countdown, resend cooldown, verify / cancel.
// Closing never happens by accident: no backdrop close, and ✕ asks to cancel the payment.
import { useEffect, useRef, useState } from 'react'
import { cancelTransaction, getTransaction, resendOtp, verifyOtp } from '../api/client.js'
import { useSecondsLeft } from '../hooks/useTimers.js'
import { formatClock, maskEmail } from '../utils/format.js'
import { Alert, Button, Money, Stepper } from './ui.jsx'

const LENGTH = 6
const RESEND_COOLDOWN = 30 // seconds; otp-service enforces the same value

export function OtpInput({ value, onChange, disabled, onComplete }) {
  const refs = useRef([])
  const digits = Array.from({ length: LENGTH }, (_, i) => value[i] || '')

  useEffect(() => { if (!disabled) refs.current[Math.min(value.length, LENGTH - 1)]?.focus() }, [disabled]) // eslint-disable-line react-hooks/exhaustive-deps

  const setAt = (i, d) => {
    const next = digits.slice()
    next[i] = d
    const joined = next.join('')
    onChange(joined)
    return joined
  }

  const onInput = (i, e) => {
    const typed = e.target.value.replace(/\D/g, '')
    if (!typed) return
    if (typed.length >= LENGTH) return onPaste(typed) // autofill of the whole code
    const joined = setAt(i, typed.slice(-1)) // box already had a digit: keep the newly typed one
    if (i < LENGTH - 1) refs.current[i + 1]?.focus()
    else if (joined.length === LENGTH) onComplete?.(joined)
  }

  const onPaste = (text) => {
    const code = text.replace(/\D/g, '').slice(0, LENGTH)
    if (!code) return
    onChange(code)
    refs.current[Math.min(code.length, LENGTH - 1)]?.focus()
    if (code.length === LENGTH) onComplete?.(code)
  }

  const onKeyDown = (i, e) => {
    if (e.key === 'Backspace') {
      e.preventDefault()
      if (digits[i]) setAt(i, '')
      else if (i > 0) { setAt(i - 1, ''); refs.current[i - 1]?.focus() }
    } else if (e.key === 'ArrowLeft' && i > 0) refs.current[i - 1]?.focus()
    else if (e.key === 'ArrowRight' && i < LENGTH - 1) refs.current[i + 1]?.focus()
  }

  return (
    <div className="flex justify-center gap-2" onPaste={(e) => { e.preventDefault(); onPaste(e.clipboardData.getData('text')) }}>
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => { refs.current[i] = el }}
          value={d}
          onChange={(e) => onInput(i, e)}
          onKeyDown={(e) => onKeyDown(i, e)}
          onFocus={(e) => e.target.select()}
          disabled={disabled}
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          maxLength={LENGTH}
          aria-label={`Digit ${i + 1}`}
          className="h-12 w-10 rounded-lg border border-slate-300 text-center text-xl font-semibold outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:bg-slate-100 sm:w-12"
        />
      ))}
    </div>
  )
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// PROCESSING = money moved, tuition commit still finishing. Poll for up to ~30 s.
async function waitWhileProcessing(txn) {
  let t = txn
  for (let i = 0; i < 15 && t.status === 'PROCESSING'; i++) {
    await sleep(2000)
    t = await getTransaction(t.id).catch(() => t)
  }
  return t
}

export default function OtpModal({ txn, tuition, email, initialExpiresIn, initialCooldown = RESEND_COOLDOWN, onResult, onCancelled }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(null) // 'verify' | 'resend' | 'cancel' | null
  const [deadline, setDeadline] = useState(() => Date.now() + (initialExpiresIn ?? 0) * 1000)
  const [resendAt, setResendAt] = useState(() => Date.now() + initialCooldown * 1000)
  const left = useSecondsLeft(deadline)
  const cooldown = useSecondsLeft(resendAt)
  const expired = left === 0

  // Transaction moved on (expired / cancelled elsewhere / finished): hand over to the result view.
  const finishWith = async (fallbackStatus) => {
    const t = await getTransaction(txn.id).catch(() => ({ ...txn, status: fallbackStatus }))
    onResult({ transaction: t, balance_after: null })
  }

  const verify = async (value = code) => {
    if (value.length !== LENGTH || busy) return
    setBusy('verify'); setError(null); setInfo(null)
    try {
      const res = await verifyOtp(txn.id, value)
      const t = res.transaction.status === 'PROCESSING' ? await waitWhileProcessing(res.transaction) : res.transaction
      onResult({ ...res, transaction: t })
    } catch (e) {
      if (e.status === 410) return finishWith('EXPIRED')
      if (e.status === 409 || e.status === 404) return finishWith('FAILED')
      setError(e.status === 429 ? `Too many attempts. Wait ${e.retryAfter || 60} seconds.` : e.message)
      setCode('')
    } finally {
      setBusy(null)
    }
  }

  const resend = async () => {
    setBusy('resend'); setError(null); setInfo(null)
    try {
      const { otp_expires_in } = await resendOtp(txn.id)
      setDeadline(Date.now() + otp_expires_in * 1000)
      setResendAt(Date.now() + RESEND_COOLDOWN * 1000)
      setCode('')
      setInfo('A new code was sent. The previous code no longer works.')
    } catch (e) {
      if (e.status === 410) return finishWith('EXPIRED')
      if (e.status === 409) return finishWith('FAILED')
      if (e.status === 429) {
        if (e.retryAfter) setResendAt(Date.now() + e.retryAfter * 1000)
        setError(e.retryAfter ? `Too many requests. Try again in ${e.retryAfter} s.` : e.message)
      } else setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  const cancel = async () => {
    if (!window.confirm('Cancel this payment?')) return
    setBusy('cancel'); setError(null)
    try {
      onCancelled(await cancelTransaction(txn.id))
    } catch (e) {
      if (e.status === 409) return finishWith('FAILED')
      setError(e.message)
      setBusy(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="otp-title">
      <div className="relative w-full max-w-md space-y-5 rounded-t-2xl bg-white p-6 shadow-xl sm:rounded-2xl">
        <button type="button" onClick={cancel} disabled={!!busy} aria-label="Cancel payment" className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">✕</button>
        <Stepper current={2} />

        <div>
          <h2 id="otp-title" className="text-lg font-semibold text-slate-900">Enter verification code</h2>
          <p className="text-sm text-slate-500">We sent a 6-digit code to {maskEmail(email) || 'your email'}</p>
        </div>

        <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
          <span className="text-slate-600">MSSV {txn.student_id}{tuition?.student_name ? ` · ${tuition.student_name}` : ''}</span>
          <Money value={txn.amount} className="font-semibold text-slate-900" />
        </div>

        <form onSubmit={(e) => { e.preventDefault(); verify() }} className="space-y-4">
          <OtpInput value={code} onChange={setCode} disabled={expired || !!busy} onComplete={verify} />

          <div className="flex items-center justify-between text-sm">
            {expired
              ? <span className="font-medium text-red-600">Code expired — resend</span>
              : <span className="text-slate-500">Code expires in <span className="tabular-nums font-medium text-slate-800">{formatClock(left)}</span></span>}
            <button
              type="button"
              onClick={resend}
              disabled={cooldown > 0 || !!busy}
              className="font-medium text-blue-600 hover:underline disabled:cursor-not-allowed disabled:text-slate-400 disabled:no-underline"
            >
              {busy === 'resend' ? 'Sending…' : cooldown > 0 ? `Resend code (${formatClock(cooldown).replace(/^0/, '')})` : 'Resend code'}
            </button>
          </div>

          {error && <Alert>{error}</Alert>}
          {info && !error && <Alert kind="info">{info}</Alert>}

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={cancel} loading={busy === 'cancel'} disabled={!!busy && busy !== 'cancel'}>Cancel payment</Button>
            <Button type="submit" loading={busy === 'verify'} disabled={code.length !== LENGTH || expired || (!!busy && busy !== 'verify')}>
              {busy === 'verify' ? 'Verifying…' : 'Verify & pay'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
