// TODO (next phase): implement the 3 sections + OTP step.
//  a) Payer profile  : read-only, from GET /api/users/me (+ balance from GET /api/accounts/me)
//  b) Tuition details: MSSV input -> debounce -> GET /api/tuitions/{mssv} (name + amount, block if PAID)
//  c) Confirmation   : balance, amount, terms checkbox; "Confirm Transaction" enabled only if tuition UNPAID,
//                      balance >= amount and terms accepted -> POST /api/transactions (new Idempotency-Key per attempt, reuse on retry)
//  d) OTP modal      : 6-digit input, 5-min countdown, resend, -> POST /api/transactions/{id}/verify-otp -> result screen
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function TuitionPaymentPage() {
  const { signOut } = useAuth()
  return (
    <main className="max-w-3xl mx-auto p-6 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Tuition Payment</h1>
        <nav className="space-x-4 text-sm">
          <Link to="/history" className="text-blue-600">History</Link>
          <button onClick={signOut} className="text-slate-600">Sign out</button>
        </nav>
      </header>
      <section className="bg-white p-4 rounded-xl shadow">Payer profile (placeholder)</section>
      <section className="bg-white p-4 rounded-xl shadow">Tuition details (placeholder)</section>
      <section className="bg-white p-4 rounded-xl shadow">Transaction confirmation (placeholder)</section>
    </main>
  )
}
