import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowRight, Edit, Printer, FileText } from 'lucide-react'
import { Button, Card } from '../components/ui'
import { useGetPaymentQuery } from '../store/api'

const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800',
  pending: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  paid: 'bg-blue-100 text-blue-800',
}

const statusLabels: Record<string, string> = {
  draft: 'مسودة',
  pending: 'قيد المراجعة',
  approved: 'معتمد',
  rejected: 'مرفوض',
  paid: 'مدفوع',
}

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

  const items = payment.items || []
  const totalCurrentBalance = items.reduce((sum: number, item: any) => sum + (item.current_balance || 0), 0)
  const totalAmount = items.reduce((sum: number, item: any) => sum + (item.amount || 0), 0)
  const totalProposed = items.reduce((sum: number, item: any) => sum + (item.proposed_amount || 0), 0)

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
          <Link to={"/payments/" + id}>
            <Button>
              <Edit className="w-4 h-4 ml-2" />
              تعديل
            </Button>
          </Link>
        </div>
      </div>

      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary-600" />
          المعلومات الأساسية
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <label className="text-sm text-gray-500">الفرع</label>
            <p className="font-medium text-gray-900">{payment.branch_name || '-'}</p>
          </div>
          <div>
            <label className="text-sm text-gray-500">البنك</label>
            <p className="font-medium text-gray-900">{payment.bank_name || '-'}</p>
          </div>
          <div>
            <label className="text-sm text-gray-500">مركز التكلفة</label>
            <p className="font-medium text-gray-900">{payment.cost_center_name || '-'}</p>
          </div>
          <div>
            <label className="text-sm text-gray-500">الحالة</label>
            <p className="mt-1">
              <span className={"px-3 py-1 rounded-full text-sm font-medium " + (statusColors[payment.status] || 'bg-gray-100')}>
                {statusLabels[payment.status] || payment.status}
              </span>
            </p>
          </div>
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="p-4 border-b bg-gray-50">
          <h2 className="text-lg font-semibold">بنود الدفع ({items.length} بند)</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-right text-sm font-semibold text-gray-700">#</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-gray-700">رقم المورد</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-gray-700">اسم المورد</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-gray-700">الرصيد الحالي</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-gray-700">دفعة المشتريات</th>
                <th className="px-4 py-3 text-right text-sm font-semibold text-gray-700">اقتراح السداد</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-500">لا توجد بنود</td>
                </tr>
              ) : (
                items.map((item: any, index: number) => (
                  <tr key={item.id || index} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-600">{index + 1}</td>
                    <td className="px-4 py-3 text-sm font-medium text-gray-900">{item.supplier_code || item.supplier || '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{item.supplier_name || '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-900 text-left font-mono">{(item.current_balance || 0).toLocaleString()}</td>
                    <td className="px-4 py-3 text-sm text-gray-900 text-left font-mono">{(item.amount || 0).toLocaleString()}</td>
                    <td className="px-4 py-3 text-sm text-primary-600 font-semibold text-left font-mono">{(item.proposed_amount || 0).toLocaleString()}</td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot className="bg-gray-100">
              <tr className="font-semibold">
                <td colSpan={3} className="px-4 py-3 text-sm text-gray-700">الإجمالي ({items.length} بند)</td>
                <td className="px-4 py-3 text-sm text-gray-900 text-left font-mono">{totalCurrentBalance.toLocaleString()}</td>
                <td className="px-4 py-3 text-sm text-gray-900 text-left font-mono">{totalAmount.toLocaleString()}</td>
                <td className="px-4 py-3 text-sm text-primary-600 text-left font-mono">{totalProposed.toLocaleString()}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </Card>
    </div>
  )
}
