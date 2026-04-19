import { Routes, Route, Navigate } from 'react-router-dom'
import { useSelector } from 'react-redux'
import { RootState } from './store'
import Layout from './components/layout/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Suppliers from './pages/Suppliers'
import Branches from './pages/Branches'
import Banks from './pages/Banks'
import CostCenters from './pages/CostCenters'
import Payments from './pages/Payments'
import PaymentForm from './pages/PaymentForm'
import PaymentDetails from './pages/PaymentDetails'
import Settings from './pages/Settings'
import Users from './pages/Users'

// Protected route wrapper - requires authentication
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const tokens = useSelector((state: RootState) => state.auth.tokens)
  if (!tokens?.access) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

// Admin-only route wrapper
function AdminRoute({ children }: { children: React.ReactNode }) {
  const user = useSelector((state: RootState) => state.auth.user)
  if (!user?.is_staff) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<Dashboard />} />
        <Route path="branches" element={<Branches />} />
        <Route path="banks" element={<Banks />} />
        <Route path="suppliers" element={<Suppliers />} />
        <Route path="cost-centers" element={<CostCenters />} />
        <Route path="payments" element={<Payments />} />
        <Route path="payments/new" element={<PaymentForm />} />
        <Route path="payments/:id" element={<PaymentDetails />} />
        <Route path="payments/:id/edit" element={<PaymentForm />} />
        <Route path="users" element={<AdminRoute><Users /></AdminRoute>} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
