import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Plus, Eye, Edit, RefreshCw } from 'lucide-react'
import { Button, Card } from '../components/ui'
import { useGetPaymentsQuery } from '../store/api'

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

export default function Payments() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const { data, isLoading, refetch } = useGetPaymentsQuery({ page })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">سجل الدفعات</h1>
          <p className="text-gray-500 mt-1">إدارة طلبات الدفع للموردين</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="w-4 h-4 ml-2" />
            تحديث
          </Button>
          <Button onClick={() => navigate('/payments/new')}>
            <Plus className="w-4 h-4 ml-2" />
            طلب جديد
          </Button>
        </div>
      </div>

      {/* Table */}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-6 py-4 text-right text-sm font-semibold text-gray-900">سجل الدفعة</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-gray-900">الفرع</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-gray-900">المستخدم</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-gray-900">التاريخ</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-gray-900">الحالة</th>
                <th className="px-6 py-4 text-right text-sm font-semibold text-gray-900">إجراءات</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                    جاري التحميل...
                  </td>
                </tr>
              ) : data?.results?.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                    لا توجد طلبات
                  </td>
                </tr>
              ) : (
                data?.results?.map((payment: any) => (
                  <tr key={payment.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <span className="font-semibold text-primary-600">#{payment.id}</span>
                    </td>
                    <td className="px-6 py-4 text-gray-900">{payment.branch_name || payment.branch}</td>
                    <td className="px-6 py-4 text-gray-600">{payment.created_by_name || 'admin'}</td>
                    <td className="px-6 py-4 text-gray-600">
                      {new Date(payment.created_at).toLocaleDateString('ar-SA')}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-3 py-1 rounded-full text-xs font-medium ${statusColors[payment.status] || 'bg-gray-100'}`}>
                        {statusLabels[payment.status] || payment.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex gap-2">
                        <Link
                          to={`/payments/${payment.id}/details`}
                          className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title="عرض التفاصيل"
                        >
                          <Eye className="w-4 h-4" />
                        </Link>
                        <Link
                          to={`/payments/${payment.id}`}
                          className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                          title="تعديل"
                        >
                          <Edit className="w-4 h-4" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {data && data.count > 20 && (
          <div className="px-6 py-4 border-t flex items-center justify-between">
            <span className="text-sm text-gray-600">
              إجمالي: {data.count} طلب
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                السابق
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(p => p + 1)}
                disabled={page * 20 >= data.count}
              >
                التالي
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
