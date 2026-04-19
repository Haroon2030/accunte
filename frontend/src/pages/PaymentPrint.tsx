import { useParams, useNavigate } from 'react-router-dom'
import { ArrowRight, Printer } from 'lucide-react'
import { Button } from '../components/ui'
import { useGetPaymentQuery } from '../store/api'

export default function PaymentPrint() {
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
        <h2 className="text-xl font-semibold text-gray-700">الطلب غير موجود</h2>
        <Button className="mt-4" onClick={() => navigate('/payments')}>
          العودة للقائمة
        </Button>
      </div>
    )
  }

  const getStatusText = (status: string) => {
    const statusMap: Record<string, string> = {
      'pending': 'جاري المعالجة',
      'approved': 'معتمد ✓',
      'rejected': 'مرفوض ✗',
    }
    return statusMap[status] || status
  }

  // Calculate totals
  const totalAmount = payment.items?.reduce((sum: number, item: any) => sum + parseFloat(item.amount || 0), 0) || 0
  const totalProposed = payment.items?.reduce((sum: number, item: any) => sum + parseFloat(item.proposed_amount || 0), 0) || 0
  const totalBalance = payment.items?.reduce((sum: number, item: any) => sum + parseFloat(item.current_balance || 0), 0) || 0

  const handlePrint = () => {
    window.print()
  }

  return (
    <>
      {/* شريط الأدوات - يختفي عند الطباعة */}
      <div className="print:hidden mb-4 flex items-center justify-between bg-white p-4 rounded-xl shadow-sm">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate(`/payments/${id}`)} className="p-2 hover:bg-gray-100 rounded-lg">
            <ArrowRight className="w-5 h-5" />
          </button>
          <h1 className="text-xl font-bold">معاينة الطباعة - طلب الدفع #{id}</h1>
        </div>
        <Button onClick={handlePrint}>
          <Printer className="w-4 h-4 ml-2" />
          طباعة
        </Button>
      </div>

      {/* نموذج الطباعة */}
      <div className="print-document bg-white p-8 print:p-0 rounded-xl shadow-sm print:shadow-none">
        {/* رأس النموذج */}
        <div className="print-header border-b-2 border-gray-800 pb-4 mb-6">
          <div className="flex justify-between items-start">
            <div className="text-right">
              <h1 className="text-2xl font-bold text-gray-900">نظام إدارة المدفوعات</h1>
              <p className="text-gray-600 mt-1">Payment Management System</p>
            </div>
            <div className="text-left">
              <div className="text-sm text-gray-600">
                <p>التاريخ: {new Date().toLocaleDateString('ar-SA')}</p>
                <p>الوقت: {new Date().toLocaleTimeString('ar-SA')}</p>
              </div>
            </div>
          </div>
        </div>

        {/* عنوان الطلب */}
        <div className="text-center mb-6">
          <h2 className="text-xl font-bold border-2 border-gray-800 inline-block px-8 py-2">
            طلب دفع رقم: {id}
          </h2>
        </div>

        {/* معلومات الطلب */}
        <div className="grid grid-cols-2 gap-4 mb-6 border border-gray-300 p-4">
          <div className="flex">
            <span className="font-bold w-28">الفرع:</span>
            <span>{payment.branch_name || '-'}</span>
          </div>
          <div className="flex">
            <span className="font-bold w-28">البنك:</span>
            <span>{payment.bank_name || '-'}</span>
          </div>
          <div className="flex">
            <span className="font-bold w-28">تاريخ الإنشاء:</span>
            <span>{new Date(payment.created_at).toLocaleDateString('ar-SA')}</span>
          </div>
          <div className="flex">
            <span className="font-bold w-28">أنشئ بواسطة:</span>
            <span>{(payment.created_by as any)?.full_name || (payment.created_by as any)?.username || '-'}</span>
          </div>
          {payment.notes && (
            <div className="flex col-span-2">
              <span className="font-bold w-28">ملاحظات:</span>
              <span>{payment.notes}</span>
            </div>
          )}
        </div>

        {/* جدول البنود */}
        <table className="print-table w-full border-collapse border border-gray-800 text-sm">
          <thead>
            <tr className="bg-gray-200">
              <th className="border border-gray-800 px-2 py-2 text-center w-10">م</th>
              <th className="border border-gray-800 px-2 py-2 text-center w-20">رقم المورد</th>
              <th className="border border-gray-800 px-2 py-2 text-right">اسم المورد</th>
              <th className="border border-gray-800 px-2 py-2 text-center w-24">رصيد المورد</th>
              <th className="border border-gray-800 px-2 py-2 text-center w-24">دفعة المشتريات</th>
              <th className="border border-gray-800 px-2 py-2 text-center w-20">سلطان</th>
              <th className="border border-gray-800 px-2 py-2 text-center w-20">المدقق</th>
              <th className="border border-gray-800 px-2 py-2 text-center w-20">المالي</th>
              <th className="border border-gray-800 px-2 py-2 text-center w-24">اقتراح السداد</th>
              <th className="border border-gray-800 px-2 py-2 text-center w-20">أبو علاء</th>
            </tr>
          </thead>
          <tbody>
            {payment.items?.map((item: any, index: number) => (
              <tr key={item.id} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                <td className="border border-gray-800 px-2 py-2 text-center">{index + 1}</td>
                <td className="border border-gray-800 px-2 py-2 text-center">{item.supplier_code || item.supplier}</td>
                <td className="border border-gray-800 px-2 py-2">{item.supplier_name}</td>
                <td className="border border-gray-800 px-2 py-2 text-center">{parseFloat(item.current_balance || 0).toLocaleString()}</td>
                <td className="border border-gray-800 px-2 py-2 text-center">{parseFloat(item.amount || 0).toLocaleString()}</td>
                <td className="border border-gray-800 px-2 py-2 text-center text-xs">{getStatusText(item.sultan_approval)}</td>
                <td className="border border-gray-800 px-2 py-2 text-center text-xs">{getStatusText(item.auditor_status)}</td>
                <td className="border border-gray-800 px-2 py-2 text-center text-xs">{getStatusText(item.cfo_approval)}</td>
                <td className="border border-gray-800 px-2 py-2 text-center">{parseFloat(item.proposed_amount || 0).toLocaleString()}</td>
                <td className="border border-gray-800 px-2 py-2 text-center text-xs">{getStatusText(item.abu_alaa_final)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-gray-200 font-bold">
              <td colSpan={3} className="border border-gray-800 px-2 py-2 text-right">
                الإجمالي ({payment.items?.length || 0} مورد)
              </td>
              <td className="border border-gray-800 px-2 py-2 text-center">{totalBalance.toLocaleString()}</td>
              <td className="border border-gray-800 px-2 py-2 text-center">{totalAmount.toLocaleString()}</td>
              <td colSpan={3} className="border border-gray-800 px-2 py-2"></td>
              <td className="border border-gray-800 px-2 py-2 text-center">{totalProposed.toLocaleString()}</td>
              <td className="border border-gray-800 px-2 py-2"></td>
            </tr>
          </tfoot>
        </table>

        {/* قسم التوقيعات */}
        <div className="mt-10 pt-6 border-t border-gray-300">
          <h3 className="font-bold mb-6 text-center">التوقيعات والاعتمادات</h3>
          <div className="grid grid-cols-4 gap-4">
            <div className="text-center border border-gray-300 p-4">
              <p className="font-bold mb-12">معد الطلب</p>
              <div className="border-t border-gray-400 pt-2">
                <p className="text-sm text-gray-600">الاسم: ..................</p>
                <p className="text-sm text-gray-600 mt-1">التوقيع: ..................</p>
                <p className="text-sm text-gray-600 mt-1">التاريخ: ..................</p>
              </div>
            </div>
            <div className="text-center border border-gray-300 p-4">
              <p className="font-bold mb-12">المدقق</p>
              <div className="border-t border-gray-400 pt-2">
                <p className="text-sm text-gray-600">الاسم: ..................</p>
                <p className="text-sm text-gray-600 mt-1">التوقيع: ..................</p>
                <p className="text-sm text-gray-600 mt-1">التاريخ: ..................</p>
              </div>
            </div>
            <div className="text-center border border-gray-300 p-4">
              <p className="font-bold mb-12">المدير المالي</p>
              <div className="border-t border-gray-400 pt-2">
                <p className="text-sm text-gray-600">الاسم: ..................</p>
                <p className="text-sm text-gray-600 mt-1">التوقيع: ..................</p>
                <p className="text-sm text-gray-600 mt-1">التاريخ: ..................</p>
              </div>
            </div>
            <div className="text-center border border-gray-300 p-4">
              <p className="font-bold mb-12">الاعتماد النهائي</p>
              <div className="border-t border-gray-400 pt-2">
                <p className="text-sm text-gray-600">الاسم: ..................</p>
                <p className="text-sm text-gray-600 mt-1">التوقيع: ..................</p>
                <p className="text-sm text-gray-600 mt-1">التاريخ: ..................</p>
              </div>
            </div>
          </div>
        </div>

        {/* تذييل الصفحة */}
        <div className="mt-8 pt-4 border-t border-gray-300 text-center text-xs text-gray-500">
          <p>تم إنشاء هذا المستند آليًا من نظام إدارة المدفوعات</p>
          <p>صفحة 1 من 1</p>
        </div>
      </div>

      {/* أنماط الطباعة */}
      <style>{`
        @media print {
          @page {
            size: A4 landscape;
            margin: 10mm;
          }
          
          body {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          
          .print-document {
            width: 100%;
            font-size: 11px;
          }
          
          .print-table th,
          .print-table td {
            padding: 4px 6px !important;
          }
          
          .print-header h1 {
            font-size: 18px;
          }
        }
      `}</style>
    </>
  )
}
