import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowRight, Edit, Printer, FileText } from 'lucide-react'
import { Button } from '../components/ui'
import { useGetPaymentQuery } from '../store/api'

export default function PaymentDetails() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: payment, isLoading, error } = useGetPaymentQuery(Number(id))

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  if (error || !payment) {
    return (
      <div className="text-center py-12">
        <FileText className="w-16 h-16 text-gray-300 mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-gray-700">الطلب غير موجود</h2>
        <p className="text-gray-500 mt-2">لم يتم العثور على طلب الدفع المطلوب</p>
        <Button className="mt-4" onClick={() => navigate('/payments')}>
          العودة للقائمة
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/payments')} className="p-2 hover:bg-gray-100 rounded-lg">
            <ArrowRight className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">طلب الدفع #{id}</h1>
            <p className="text-gray-500 mt-1">تم الإنشاء: {new Date(payment.created_at).toLocaleDateString('ar-SA')}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => window.print()}>
            <Printer className="w-4 h-4 ml-2" />
            طباعة
          </Button>
          <Link to={"/payments/" + id + "/edit"}>
            <Button>
              <Edit className="w-4 h-4 ml-2" />
              تعديل
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}
