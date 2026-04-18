import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowRight, Edit, Printer, FileText } from 'lucide-react'
import { Button, Card } from '../components/ui'
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

  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, { label: string; color: string }> = {
      'pending': { label: 'جاري المعالجة', color: 'bg-yellow-100 text-yellow-800' },
      'approved': { label: 'معتمد', color: 'bg-green-100 text-green-800' },
      'rejected': { label: 'مرفوض', color: 'bg-red-100 text-red-800' },
    }
    const s = statusMap[status] || { label: status, color: 'bg-gray-100 text-gray-800' }
    return <span className={`px-2 py-1 rounded-full text-xs font-medium ${s.color}`}>{s.label}</span>
  }

  // Calculate totals
  const totalAmount = payment.items?.reduce((sum: number, item: any) => sum + parseFloat(item.amount || 0), 0) || 0
  const totalProposed = payment.items?.reduce((sum: number, item: any) => sum + parseFloat(item.proposed_amount || 0), 0) || 0
  const totalBalance = payment.items?.reduce((sum: number, item: any) => sum + parseFloat(item.current_balance || 0), 0) || 0

  return (
    <div className="space-y-6">
      {/* Header */}
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

      {/* Payment Info */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">معلومات الطلب</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm text-gray-500">الفرع</label>
            <p className="font-medium">{payment.branch_name || '-'}</p>
          </div>
          <div>
            <label className="block text-sm text-gray-500">البنك</label>
            <p className="font-medium">{payment.bank_name || '-'}</p>
          </div>
          <div>
            <label className="block text-sm text-gray-500">الحالة</label>
            <p className="font-medium">{(payment as any).status_display || payment.status}</p>
          </div>
          <div>
            <label className="block text-sm text-gray-500">أنشأ بواسطة</label>
            <p className="font-medium">{(payment.created_by as any)?.full_name || (payment.created_by as any)?.username || '-'}</p>
          </div>
        </div>
        {payment.notes && (
          <div className="mt-4">
            <label className="block text-sm text-gray-500">ملاحظات</label>
            <p className="font-medium">{payment.notes}</p>
          </div>
        )}
      </Card>

      {/* Items Table */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">بنود الدفع ({payment.items?.length || 0} بند)</h2>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">#</th>
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">رقم المورد</th>
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">اسم المورد</th>
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">الدفعة المرفوعة</th>
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">دفعة المشتريات</th>
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">اعتماد سلطان</th>
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">حالة المدقق</th>
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">المدير المالي</th>
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">اقتراح السداد</th>
                <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">اعتماد أبو علاء</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {payment.items?.map((item: any, index: number) => (
                <tr key={item.id} className="hover:bg-gray-50">
                  <td className="px-3 py-3 text-sm text-gray-600">{index + 1}</td>
                  <td className="px-3 py-3 text-sm">{item.supplier_code || item.supplier}</td>
                  <td className="px-3 py-3 text-sm font-medium">{item.supplier_name}</td>
                  <td className="px-3 py-3 text-sm">{parseFloat(item.current_balance || 0).toLocaleString()}</td>
                  <td className="px-3 py-3 text-sm">{parseFloat(item.amount || 0).toLocaleString()}</td>
                  <td className="px-3 py-3">{getStatusBadge(item.sultan_approval)}</td>
                  <td className="px-3 py-3">{getStatusBadge(item.auditor_status)}</td>
                  <td className="px-3 py-3">{getStatusBadge(item.cfo_approval)}</td>
                  <td className="px-3 py-3 text-sm">{parseFloat(item.proposed_amount || 0).toLocaleString()}</td>
                  <td className="px-3 py-3">{getStatusBadge(item.abu_alaa_final)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50">
              <tr>
                <td colSpan={3} className="px-3 py-3 text-sm font-semibold text-gray-700">الإجمالي ({payment.items?.length || 0} بند)</td>
                <td className="px-3 py-3 text-sm font-semibold">{totalBalance.toLocaleString()}</td>
                <td className="px-3 py-3 text-sm font-semibold">{totalAmount.toLocaleString()}</td>
                <td colSpan={3}></td>
                <td className="px-3 py-3 text-sm font-semibold">{totalProposed.toLocaleString()}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </Card>
    </div>
  )
}
