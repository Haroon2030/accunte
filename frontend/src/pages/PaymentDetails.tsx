import { useParams } from 'react-router-dom'

export default function PaymentDetails() {
  const { id } = useParams()
  
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">تفاصيل طلب الدفع #{id}</h1>
      <p className="text-gray-500">عرض تفاصيل طلب الدفع</p>
    </div>
  )
}
