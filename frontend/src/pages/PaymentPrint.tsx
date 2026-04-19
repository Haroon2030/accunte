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
      <div className="print:hidden flex items-center justify-center h-screen bg-gray-100">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  if (error || !payment) {
    return (
      <div className="print:hidden text-center py-12 bg-gray-100 h-screen flex flex-col items-center justify-center">
        <h2 className="text-xl font-semibold text-gray-700">الطلب غير موجود</h2>
        <Button className="mt-4" onClick={() => navigate('/payments')}>
          العودة للقائمة
        </Button>
      </div>
    )
  }

  // Calculate totals
  const totalAmount = payment.items?.reduce((sum: number, item: any) => sum + parseFloat(item.amount || 0), 0) || 0
  const totalProposed = payment.items?.reduce((sum: number, item: any) => sum + parseFloat(item.proposed_amount || 0), 0) || 0

  const handlePrint = () => {
    window.print()
  }

  return (
    <>
      {/* شريط الأدوات - يختفي عند الطباعة */}
      <div className="print:hidden fixed top-0 left-0 right-0 z-50 bg-white shadow-md p-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(`/payments/${id}`)} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
            <ArrowRight className="w-5 h-5" />
          </button>
          <span className="text-gray-600">معاينة المستند الرسمي</span>
        </div>
        <Button onClick={handlePrint} className="px-6">
          <Printer className="w-4 h-4 ml-2" />
          طباعة
        </Button>
      </div>

      {/* المستند الرسمي */}
      <div className="print:m-0 print:p-0 min-h-screen bg-gray-100 print:bg-white pt-16 print:pt-0 pb-8 print:pb-0" dir="rtl">
        <div className="max-w-[210mm] mx-auto bg-white print:max-w-none print:shadow-none shadow-xl">
          
          {/* الصفحة */}
          <div className="p-8 print:p-[15mm]">
            
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
                <tr className="bg-gray-800 text-white">
                  <th className="border border-gray-600 px-3 py-2 text-center w-10">م</th>
                  <th className="border border-gray-600 px-3 py-2 text-center">رقم المورد</th>
                  <th className="border border-gray-600 px-3 py-2 text-right">اسم المورد</th>
                  <th className="border border-gray-600 px-3 py-2 text-center">دفعة المشتريات</th>
                  <th className="border border-gray-600 px-3 py-2 text-center">المبلغ المقترح</th>
                </tr>
              </thead>
              <tbody>
                {payment.items?.map((item: any, index: number) => (
                  <tr key={item.id} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                    <td className="border border-gray-300 px-3 py-2.5 text-center font-medium">{index + 1}</td>
                    <td className="border border-gray-300 px-3 py-2.5 text-center">{item.supplier_code || item.supplier}</td>
                    <td className="border border-gray-300 px-3 py-2.5 font-medium">{item.supplier_name}</td>
                    <td className="border border-gray-300 px-3 py-2.5 text-center">{parseFloat(item.amount || 0).toLocaleString('ar-SA')} ر.س</td>
                    <td className="border border-gray-300 px-3 py-2.5 text-center font-semibold text-primary-700">{parseFloat(item.proposed_amount || 0).toLocaleString('ar-SA')} ر.س</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-gray-800 text-white font-bold">
                  <td colSpan={3} className="border border-gray-600 px-3 py-3 text-right">
                    الإجمالي ({payment.items?.length || 0} مورد)
                  </td>
                  <td className="border border-gray-600 px-3 py-3 text-center">{totalAmount.toLocaleString('ar-SA')} ر.س</td>
                  <td className="border border-gray-600 px-3 py-3 text-center">{totalProposed.toLocaleString('ar-SA')} ر.س</td>
                </tr>
              </tfoot>
            </table>

            {/* ملخص المبالغ */}
            <div className="bg-gray-50 border-2 border-gray-300 rounded-lg p-4 mb-8">
              <div className="flex justify-around text-center">
                <div>
                  <p className="text-gray-500 text-sm">إجمالي المشتريات</p>
                  <p className="text-xl font-bold text-gray-800">{totalAmount.toLocaleString('ar-SA')} ر.س</p>
                </div>
                <div className="border-r border-gray-300"></div>
                <div>
                  <p className="text-gray-500 text-sm">إجمالي المبلغ المقترح</p>
                  <p className="text-xl font-bold text-primary-700">{totalProposed.toLocaleString('ar-SA')} ر.س</p>
                </div>
                <div className="border-r border-gray-300"></div>
                <div>
                  <p className="text-gray-500 text-sm">عدد الموردين</p>
                  <p className="text-xl font-bold text-gray-800">{payment.items?.length || 0}</p>
                </div>
              </div>
            </div>

            {/* التوقيعات */}
            <div className="grid grid-cols-3 gap-6 mt-10">
              <div className="text-center">
                <p className="font-bold text-gray-700 mb-16">المُعد</p>
                <div className="border-t-2 border-gray-400 pt-2 mx-4">
                  <p className="text-xs text-gray-500">التوقيع والتاريخ</p>
                </div>
              </div>
              <div className="text-center">
                <p className="font-bold text-gray-700 mb-16">المدقق</p>
                <div className="border-t-2 border-gray-400 pt-2 mx-4">
                  <p className="text-xs text-gray-500">التوقيع والتاريخ</p>
                </div>
              </div>
              <div className="text-center">
                <p className="font-bold text-gray-700 mb-16">الاعتماد</p>
                <div className="border-t-2 border-gray-400 pt-2 mx-4">
                  <p className="text-xs text-gray-500">التوقيع والتاريخ</p>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      {/* أنماط الطباعة */}
      <style>{`
        @media print {
          @page {
            size: A4 portrait;
            margin: 0;
          }
          
          * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          
          body {
            margin: 0;
            padding: 0;
          }
          
          .bg-gray-800 {
            background-color: #1f2937 !important;
          }
          
          .text-white {
            color: white !important;
          }
          
          .bg-gray-50 {
            background-color: #f9fafb !important;
          }
        }
      `}</style>
    </>
  )
}
