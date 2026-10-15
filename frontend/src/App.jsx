import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from './pages/LoginPage.jsx'
import TuitionPaymentPage from './pages/TuitionPaymentPage.jsx'
import HistoryPage from './pages/HistoryPage.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/pay" element={<ProtectedRoute><TuitionPaymentPage /></ProtectedRoute>} />
      <Route path="/history" element={<ProtectedRoute><HistoryPage /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/pay" replace />} />
    </Routes>
  )
}
