import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Plus, Eye, Edit, RefreshCw, Download, FileText, Calendar, User, Building2 } from 'lucide-react'
import * as XLSX from 'xlsx'
import { saveAs } from 'file-saver'
import toast from 'react-hot-toast'
import { Button } from '../components/ui'
import { useGetPaymentsQuery } from '../store/api'

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
  const { data: allPaymentsData } = useGetPaymentsQuery({ page: 1, page_size: 10000 })

  // Export to Excel function
  const exportToExcel = () => {
    const allPayments = allPaymentsData?.results || data?.results || []
    
    if (allPayments.length === 0) {
      toast.error('لا توجد بيانات للتصدير')
      return
    }

    // Prepare data for export
    const exportData = allPayments.map((payment: any, index: number) => ({
      '#': index + 1,
      'رقم الطلب': payment.id,
      'الفرع': payment.branch_name || payment.branch,
      'المستخدم': payment.created_by_name || 'admin',
      'الحالة': statusLabels[payment.status] || payment.status,
      'تاريخ الإنشاء': new Date(payment.created_at).toLocaleDateString('ar-SA'),
    }))

    // Create workbook and worksheet
    const wb = XLSX.utils.book_new()
    const ws = XLSX.utils.json_to_sheet(exportData)

    // Set RTL direction
    ws['!dir'] = 'rtl'

    // Set column widths
    ws['!cols'] = [
      { wch: 5 },   // #
      { wch: 12 },  // رقم الطلب
      { wch: 25 },  // الفرع
      { wch: 15 },  // المستخدم
      { wch: 15 },  // الحالة
      { wch: 15 },  // تاريخ الإنشاء
    ]

    // Add worksheet to workbook
    XLSX.utils.book_append_sheet(wb, ws, 'طلبات الدفع')

    // Generate Excel file
    const excelBuffer = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    const dataBlob = new Blob([excelBuffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    
    // Save file with date
    const today = new Date().toLocaleDateString('ar-SA').replace(/\//g, '-')
    saveAs(dataBlob, `طلبات_الدفع_${today}.xlsx`)
    
    toast.success('تم تصدير البيانات بنجاح')
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">سجل الدفعات</h1>
          <p className="text-gray-500 mt-1">إدارة طلبات الدفع للموردين</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={exportToExcel}>
            <Download className="w-4 h-4 ml-2" />
            تصدير Excel
          </Button>
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

      {/* Modern Table */}
      <div className="modern-table-container w-full">
        <div className="overflow-x-auto">
          <table className="modern-table w-full">
            <thead>
              <tr>
                <th>سجل الدفعة</th>
                <th>الفرع</th>
                <th>المستخدم</th>
                <th>التاريخ</th>
                <th>الحالة</th>
                <th>إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={6}>
                    <div className="table-empty-state">
                      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4" />
                      <p className="text">جاري التحميل...</p>
                    </div>
                  </td>
                </tr>
              ) : data?.results?.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="table-empty-state">
                      <FileText className="icon" />
                      <p className="text">لا توجد طلبات دفع</p>
                    </div>
                  </td>
                </tr>
              ) : (
                data?.results?.map((payment: any) => (
                  <tr key={payment.id}>
                    <td>
                      <span className="payment-id-badge">#{payment.id}</span>
                    </td>
                    <td>
                      <div className="flex items-center justify-center gap-2">
                        <div className="table-icon-box primary w-8 h-8">
                          <Building2 className="w-4 h-4" />
                        </div>
                        <span className="font-medium text-slate-800">{payment.branch_name || payment.branch}</span>
                      </div>
                    </td>
                    <td>
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center">
                          <User className="w-3.5 h-3.5 text-slate-600" />
                        </div>
                        <span className="text-slate-600">{payment.created_by_name || 'admin'}</span>
                      </div>
                    </td>
                    <td>
                      <div className="flex items-center justify-center gap-2 text-slate-600">
                        <Calendar className="w-4 h-4 text-slate-400" />
                        <span>{new Date(payment.created_at).toLocaleDateString('ar-SA')}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`payment-status-badge ${payment.status}`}>
                        {statusLabels[payment.status] || payment.status}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center justify-center gap-1">
                        <Link
                          to={`/payments/${payment.id}`}
                          className="action-btn edit"
                          title="عرض التفاصيل"
                        >
                          <Eye className="w-4 h-4" />
                        </Link>
                        <Link
                          to={`/payments/${payment.id}/edit`}
                          className="action-btn edit"
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
      </div>

      {/* Pagination */}
      {data && data.count > 20 && (
        <div className="modern-pagination">
          <Button
            variant="outline"
            size="sm"
            className="page-btn"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            السابق
          </Button>
          <span className="page-info text-slate-600 bg-slate-100 px-4 py-2 rounded-xl text-sm font-medium">
            صفحة {page} من {Math.ceil(data.count / 20)} • إجمالي {data.count} طلب
          </span>
          <Button
            variant="outline"
            size="sm"
            className="page-btn"
            onClick={() => setPage(p => p + 1)}
            disabled={page * 20 >= data.count}
          >
            التالي
          </Button>
        </div>
      )}
    </div>
  )
}
