import { Routes, Route, Navigate } from 'react-router-dom'
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

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="branches" element={<Branches />} />
        <Route path="banks" element={<Banks />} />
        <Route path="suppliers" element={<Suppliers />} />
        <Route path="cost-centers" element={<CostCenters />} />
        <Route path="payments" element={<Payments />} />
        <Route path="payments/new" element={<PaymentForm />} />
        <Route path="payments/:id" element={<PaymentDetails />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
