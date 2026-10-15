// Thin fetch wrapper. Same-origin: nginx (or the Vite dev proxy) forwards /api/* to the gateway.
const TOKEN_KEY = 'token'

export const getToken = () => sessionStorage.getItem(TOKEN_KEY)
export const setToken = (t) => (t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY))

export async function api(path, { method = 'GET', body, headers = {} } = {}) {
  const token = getToken()
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const err = new Error(data?.detail || res.statusText)
    err.status = res.status
    throw err
  }
  return data
}

// Endpoint helpers (see docs/api/endpoints.md)
export const login = (username, password) => api('/auth/login', { method: 'POST', body: { username, password } })
export const getProfile = () => api('/users/me')
export const getAccount = () => api('/accounts/me')
export const getTuition = (mssv) => api(`/tuitions/${encodeURIComponent(mssv)}`)
export const initiateTransaction = (studentId, idempotencyKey) =>
  api('/transactions', { method: 'POST', body: { student_id: studentId }, headers: { 'Idempotency-Key': idempotencyKey } })
export const verifyOtp = (txnId, otp) => api(`/transactions/${txnId}/verify-otp`, { method: 'POST', body: { otp } })
export const resendOtp = (txnId) => api(`/transactions/${txnId}/resend-otp`, { method: 'POST' })
export const getHistory = () => api('/transactions')
