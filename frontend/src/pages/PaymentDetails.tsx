import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowRight, Edit, Printer, FileText, Download, Building2, CreditCard, User, Calendar, Clock, FileSpreadsheet } from 'lucide-react'
import * as XLSX from 'xlsx'
import toast from 'react-hot-toast'
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

  // Direct print function
  const handlePrint = () => {
    window.print()
  }

  // Export to Excel function
  const exportToExcel = () => {
    if (!payment.items || payment.items.length === 0) {
      toast.error('لا توجد بيانات للتصدير')
      return
    }

    const getStatusLabel = (status: string) => {
      const statusMap: Record<string, string> = {
        'pending': 'جاري المعالجة',
        'approved': 'معتمد',
        'rejected': 'مرفوض',
      }
      return statusMap[status] || status
    }

    // Prepare data for export
    const exportData = payment.items.map((item: any, index: number) => ({
      '#': index + 1,
      'رقم المورد': item.supplier_code || item.supplier,
      'اسم المورد': item.supplier_name,
      'رصيد المورد': parseFloat(item.current_balance || 0),
      'دفعة المشتريات': parseFloat(item.amount || 0),
      'اعتماد سلطان': getStatusLabel(item.sultan_approval),
      'حالة المدقق': getStatusLabel(item.auditor_status),
      'المدير المالي': getStatusLabel(item.cfo_approval),
      'اقتراح السداد': parseFloat(item.proposed_amount || 0),
      'اعتماد أبو علاء': getStatusLabel(item.abu_alaa_final),
    }))

    // Add totals row
    exportData.push({
      '#': '' as any,
      'رقم المورد': '',
      'اسم المورد': 'الإجمالي',
      'رصيد المورد': totalBalance,
      'دفعة المشتريات': totalAmount,
      'اعتماد سلطان': '',
      'حالة المدقق': '',
      'المدير المالي': '',
      'اقتراح السداد': totalProposed,
      'اعتماد أبو علاء': '',
    })

    // Create workbook and worksheet
    const wb = XLSX.utils.book_new()
    const ws = XLSX.utils.json_to_sheet(exportData)

    // Set RTL direction
    ws['!dir'] = 'rtl'

    // Set column widths
    ws['!cols'] = [
      { wch: 5 },   // #
      { wch: 12 },  // رقم المورد
      { wch: 35 },  // اسم المورد
      { wch: 15 },  // رصيد المورد
      { wch: 15 },  // دفعة المشتريات
      { wch: 15 },  // اعتماد سلطان
      { wch: 15 },  // حالة المدقق
      { wch: 15 },  // المدير المالي
      { wch: 15 },  // اقتراح السداد
      { wch: 15 },  // اعتماد أبو علاء
    ]

    // Add worksheet to workbook
    XLSX.utils.book_append_sheet(wb, ws, `طلب دفع #${id}`)

    // Generate and download Excel file directly
    const branchName = payment.branch_name || 'طلب'
    XLSX.writeFile(wb, `طلب_دفع_${id}_${branchName}.xlsx`)
    
    toast.success('تم تصدير البيانات بنجاح')
  }

  return (
    <>
    {/* قسم الطباعة - يظهر فقط عند الطباعة */}
    <div className="print-section hidden print:block" dir="rtl">
      <style>{`
        @media print {
          @page { size: A4 portrait; margin: 10mm; }
          * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
          body * { visibility: hidden; }
          .print-section, .print-section * { visibility: visible; }
          .print-section { position: absolute; left: 0; top: 0; width: 100%; }
          .no-print { display: none !important; }
        }
      `}</style>
      
      {/* الترويسة */}
      <div className="border-b-4 border-double border-gray-800 pb-4 mb-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">كشف مستحقات الموردين</h1>
            <p className="text-gray-500 text-sm mt-1">Suppliers Payment Statement</p>
          </div>
          <div className="text-left text-sm">
            <p className="text-gray-600">رقم الطلب: <span className="font-bold text-gray-900">{id}</span></p>
            <p className="text-gray-600">التاريخ: <span className="font-bold">{new Date(payment.created_at).toLocaleDateString('ar-SA')}</span></p>
          </div>
        </div>
      </div>

      {/* معلومات أساسية */}
      <div className="flex justify-between mb-6 text-sm">
        <div><span className="text-gray-500">الفرع:</span> <span className="font-semibold">{payment.branch_name || '-'}</span></div>
        <div><span className="text-gray-500">البنك:</span> <span className="font-semibold">{payment.bank_name || '-'}</span></div>
      </div>

      {/* جدول البنود */}
      <table className="w-full border-collapse text-sm mb-6">
        <thead>
          <tr style={{ backgroundColor: '#1f2937', color: 'white' }}>
            <th className="border border-gray-600 px-3 py-2 text-center w-10">م</th>
            <th className="border border-gray-600 px-3 py-2 text-center">رقم المورد</th>
            <th className="border border-gray-600 px-3 py-2 text-right">اسم المورد</th>
            <th className="border border-gray-600 px-3 py-2 text-center">دفعة المشتريات</th>
            <th className="border border-gray-600 px-3 py-2 text-center">المبلغ المقترح</th>
          </tr>
        </thead>
        <tbody>
          {payment.items?.map((item: any, index: number) => (
            <tr key={item.id} style={{ backgroundColor: index % 2 === 0 ? 'white' : '#f9fafb' }}>
              <td className="border border-gray-300 px-3 py-2.5 text-center font-medium">{index + 1}</td>
              <td className="border border-gray-300 px-3 py-2.5 text-center">{item.supplier_code || item.supplier}</td>
              <td className="border border-gray-300 px-3 py-2.5 font-medium">{item.supplier_name}</td>
              <td className="border border-gray-300 px-3 py-2.5 text-center">{parseFloat(item.amount || 0).toLocaleString('ar-SA')} ر.س</td>
              <td className="border border-gray-300 px-3 py-2.5 text-center font-semibold" style={{ color: '#1d4ed8' }}>{parseFloat(item.proposed_amount || 0).toLocaleString('ar-SA')} ر.س</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ backgroundColor: '#1f2937', color: 'white', fontWeight: 'bold' }}>
            <td colSpan={3} className="border border-gray-600 px-3 py-3 text-right">
              الإجمالي ({payment.items?.length || 0} مورد)
            </td>
            <td className="border border-gray-600 px-3 py-3 text-center">{totalAmount.toLocaleString('ar-SA')} ر.س</td>
            <td className="border border-gray-600 px-3 py-3 text-center">{totalProposed.toLocaleString('ar-SA')} ر.س</td>
          </tr>
        </tfoot>
      </table>
    </div>

    {/* المحتوى العادي - يختفي عند الطباعة */}
    <div className="space-y-6 no-print print:hidden">
      {/* Header بتصميم مطابق للصورة */}
      <div className="bg-[#0a8bc2] rounded-2xl p-5 md:p-6 text-white shadow-lg">
        <div className="flex items-center justify-between">
          {/* الجانب الأيمن - العنوان والمعلومات */}
          <div className="flex items-center gap-4">
            <button 
              onClick={() => navigate('/payments')} 
              className="p-2 hover:bg-white/20 rounded-xl transition-colors"
            >
              <ArrowRight className="w-6 h-6" />
            </button>
            <div className="bg-white/20 p-3 rounded-xl">
              <FileSpreadsheet className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">طلب الدفع #{id}</h1>
              <div className="flex items-center gap-2 mt-1 text-white/80">
                <Calendar className="w-4 h-4" />
                <span className="text-sm">تم الإنشاء: {new Date(payment.created_at).toLocaleDateString('ar-SA')}</span>
              </div>
            </div>
          </div>
          
          {/* الجانب الأيسر - الأزرار */}
          <div className="flex items-center gap-3">
            <button 
              onClick={exportToExcel} 
              className="flex items-center gap-2 bg-transparent border border-white/40 text-white hover:bg-white/10 px-4 py-2.5 rounded-xl transition-colors text-sm font-medium"
            >
              <Download className="w-4 h-4" />
              تصدير Excel
            </button>
            <button 
              onClick={handlePrint} 
              className="flex items-center gap-2 bg-transparent border border-white/40 text-white hover:bg-white/10 px-4 py-2.5 rounded-xl transition-colors text-sm font-medium"
            >
              <Printer className="w-4 h-4" />
              طباعة
            </button>
            <Link to={`/payments/${id}/edit`}>
              <button className="flex items-center gap-2 bg-white text-gray-700 hover:bg-gray-100 px-4 py-2.5 rounded-xl transition-colors text-sm font-medium">
                <Edit className="w-4 h-4" />
                تعديل
              </button>
            </Link>
          </div>
        </div>
      </div>

      {/* بطاقات المعلومات - تصميم مطابق للصورة */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* الفرع */}
        <div className="bg-white rounded-2xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center gap-4">
            <div className="bg-emerald-50 p-3 rounded-xl">
              <Building2 className="w-6 h-6 text-emerald-500" />
            </div>
            <div className="text-right flex-1">
              <p className="text-sm text-gray-400">الفرع</p>
              <p className="font-bold text-gray-900 text-lg">{payment.branch_name || '-'}</p>
            </div>
          </div>
        </div>
        
        {/* البنك */}
        <div className="bg-white rounded-2xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center gap-4">
            <div className="bg-emerald-50 p-3 rounded-xl">
              <CreditCard className="w-6 h-6 text-emerald-500" />
            </div>
            <div className="text-right flex-1">
              <p className="text-sm text-gray-400">البنك</p>
              <p className="font-bold text-gray-900 text-lg">{payment.bank_name || '-'}</p>
            </div>
          </div>
        </div>
        
        {/* الحالة */}
        <div className="bg-white rounded-2xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center gap-4">
            <div className="bg-amber-50 p-3 rounded-xl">
              <Clock className="w-6 h-6 text-amber-500" />
            </div>
            <div className="text-right flex-1">
              <p className="text-sm text-gray-400">الحالة</p>
              <p className="font-bold text-amber-600 text-lg">{(payment as any).status_display || payment.status || 'مسودة'}</p>
            </div>
          </div>
        </div>
        
        {/* أنشئ بواسطة */}
        <div className="bg-white rounded-2xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center gap-4">
            <div className="bg-purple-50 p-3 rounded-xl">
              <User className="w-6 h-6 text-purple-500" />
            </div>
            <div className="text-right flex-1">
              <p className="text-sm text-gray-400">أنشئ بواسطة</p>
              <p className="font-bold text-gray-900 text-lg">{(payment.created_by as any)?.full_name || (payment.created_by as any)?.username || 'admin'}</p>
            </div>
          </div>
        </div>
      </div>

      {/* جدول البنود - تصميم مطابق للصورة */}
      <div className="bg-white rounded-2xl overflow-hidden shadow-sm border border-gray-100">
        <div className="bg-[#1e3a5f] text-white px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="w-5 h-5" />
              <h2 className="text-lg font-bold">بنود الدفع</h2>
            </div>
            <span className="bg-gray-600 px-4 py-1.5 rounded-full text-sm font-medium">{payment.items?.length || 0} مورد</span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-4 text-center text-sm font-semibold text-gray-600">#</th>
                <th className="px-4 py-4 text-center text-sm font-semibold text-gray-600">رقم المورد</th>
                <th className="px-4 py-4 text-right text-sm font-semibold text-gray-600">اسم المورد</th>
                <th className="px-4 py-4 text-center text-sm font-semibold text-gray-600">رصيد المورد</th>
                <th className="px-4 py-4 text-center text-sm font-semibold text-gray-600">دفعة المشتريات</th>
                <th className="px-4 py-4 text-center text-sm font-semibold text-gray-600">اعتماد سلطان</th>
                <th className="px-4 py-4 text-center text-sm font-semibold text-gray-600">حالة المدقق</th>
                <th className="px-4 py-4 text-center text-sm font-semibold text-gray-600">المدير المالي</th>
                <th className="px-4 py-4 text-center text-sm font-semibold text-gray-600">اقتراح السداد</th>
                <th className="px-4 py-4 text-center text-sm font-semibold text-gray-600">اعتماد أبو علاء</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {payment.items?.map((item: any, index: number) => (
                <tr key={item.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-4 text-center">
                    <span className="bg-gray-100 text-gray-700 w-8 h-8 rounded-full inline-flex items-center justify-center font-bold text-sm">{index + 1}</span>
                  </td>
                  <td className="px-4 py-4 text-center">
                    <span className="bg-blue-50 text-blue-700 px-3 py-1.5 rounded-lg font-mono text-sm border border-blue-100">{item.supplier_code || item.supplier}</span>
                  </td>
                  <td className="px-4 py-4 font-semibold text-gray-900">{item.supplier_name}</td>
                  <td className="px-4 py-4 text-center font-medium text-gray-700">{parseFloat(item.current_balance || 0).toLocaleString('ar-SA')}</td>
                  <td className="px-4 py-4 text-center font-medium text-gray-700">{parseFloat(item.amount || 0).toLocaleString('ar-SA')}</td>
                  <td className="px-4 py-4 text-center">{getStatusBadge(item.sultan_approval)}</td>
                  <td className="px-4 py-4 text-center">{getStatusBadge(item.auditor_status)}</td>
                  <td className="px-4 py-4 text-center">{getStatusBadge(item.cfo_approval)}</td>
                  <td className="px-4 py-4 text-center">
                    <span className="bg-green-100 text-green-700 px-3 py-1.5 rounded-lg font-bold border border-green-200">{parseFloat(item.proposed_amount || 0).toLocaleString('ar-SA')}</span>
                  </td>
                  <td className="px-4 py-4 text-center">{getStatusBadge(item.abu_alaa_final)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-[#1e3a5f] text-white">
                <td colSpan={3} className="px-4 py-4 font-bold text-right">الإجمالي ({payment.items?.length || 0} مورد)</td>
                <td className="px-4 py-4 font-bold text-center">{totalBalance.toLocaleString('ar-SA')}</td>
                <td className="px-4 py-4 font-bold text-center">{totalAmount.toLocaleString('ar-SA')}</td>
                <td colSpan={3}></td>
                <td className="px-4 py-4 font-bold text-center text-green-300">{totalProposed.toLocaleString('ar-SA')}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </div>
    </>
  )
}
