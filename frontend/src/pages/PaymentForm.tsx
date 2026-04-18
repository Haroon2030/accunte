import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Plus, Trash2, Save, ArrowRight, Search, X, User, Building2 } from 'lucide-react'
import { Button, Card, Input } from '../components/ui'
import {
  useGetBranchesQuery,
  useGetBanksQuery,
  useGetCostCentersQuery,
  useGetAllSuppliersQuery,
  useGetPaymentQuery,
  useCreatePaymentMutation,
  useUpdatePaymentMutation,
} from '../store/api'
import toast from 'react-hot-toast'

interface PaymentItem {
  id?: number
  supplier: number | null
  supplier_name?: string
  current_balance: number
  amount: number
  sultan_approval: string
  auditor_status: string
  financial_manager_approval: string
  proposed_amount: number
  abu_alaa_approval: string
  cost_center?: number
  cost_center_name?: string
}

export default function PaymentForm() {
  const { id } = useParams()
  const navigate = useNavigate()
  const isEditing = Boolean(id)

  // Form state
  const [branch, setBranch] = useState<number | null>(null)
  const [bank, setBank] = useState<number | null>(null)
  const [bankAccountNumber, setBankAccountNumber] = useState('')
  const [analyticalAccount, setAnalyticalAccount] = useState('')
  const [supplierAccountNumber, setSupplierAccountNumber] = useState('')
  const [costCenter, setCostCenter] = useState<number | null>(null)
  const [notes, setNotes] = useState('')
  const [items, setItems] = useState<PaymentItem[]>([
    { supplier: null, current_balance: 0, amount: 0, sultan_approval: 'جاري المعالجة', auditor_status: 'جاري المعالجة', financial_manager_approval: 'جاري المعالجة', proposed_amount: 0, abu_alaa_approval: 'جاري المعالجة' }
  ])
  
  // Supplier Modal state
  const [supplierModalOpen, setSupplierModalOpen] = useState(false)
  const [supplierModalIndex, setSupplierModalIndex] = useState<number | null>(null)
  const [supplierSearchQuery, setSupplierSearchQuery] = useState('')
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Queries
  const { data: branchesData } = useGetBranchesQuery({ page: 1 })
  const { data: banksData } = useGetBanksQuery({ page: 1 })
  const { data: costCentersData } = useGetCostCentersQuery({ page: 1 })
  const { data: allSuppliers = [] } = useGetAllSuppliersQuery()
  const { data: paymentData, isLoading: paymentLoading } = useGetPaymentQuery(Number(id), { skip: !id })

  // Mutations
  const [createPayment, { isLoading: creating }] = useCreatePaymentMutation()
  const [updatePayment, { isLoading: updating }] = useUpdatePaymentMutation()

  // Load existing payment data
  useEffect(() => {
    if (paymentData && isEditing) {
      setBranch(paymentData.branch || null)
      setBank(paymentData.bank || null)
      setBankAccountNumber((paymentData as any).bank_account_number || '')
      setAnalyticalAccount((paymentData as any).analytical_account || '')
      setSupplierAccountNumber((paymentData as any).supplier_account || '')
      setCostCenter((paymentData as any).cost_center || null)
      setNotes(paymentData.notes || '')
      if (paymentData.items && paymentData.items.length > 0) {
        setItems(paymentData.items.map(item => ({
          id: item.id,
          supplier: (item as any).supplier || null,
          supplier_name: (item as any).supplier_name || '',
          current_balance: (item as any).current_balance || 0,
          amount: (item as any).amount || 0,
          sultan_approval: (item as any).sultan_approval || 'جاري المعالجة',
          auditor_status: (item as any).auditor_status || 'جاري المعالجة',
          financial_manager_approval: (item as any).financial_manager_approval || 'جاري المعالجة',
          proposed_amount: (item as any).proposed_amount || 0,
          abu_alaa_approval: (item as any).abu_alaa_approval || 'جاري المعالجة',
          cost_center: (item as any).cost_center,
          cost_center_name: (item as any).cost_center_name,
        })))
      }
    }
  }, [paymentData, isEditing])

  // Get default cost center
  const getDefaultCostCenter = () => {
    if (costCentersData?.results && costCentersData.results.length > 0) {
      return costCentersData.results[0]
    }
    return null
  }

  // Auto-assign cost center when cost centers are loaded
  useEffect(() => {
    if (costCentersData?.results && costCentersData.results.length > 0 && !isEditing) {
      const defaultCC = costCentersData.results[0]
      setItems(prevItems => prevItems.map(item => {
        if (!item.cost_center) {
          return {
            ...item,
            cost_center: defaultCC.id,
            cost_center_name: defaultCC.name
          }
        }
        return item
      }))
    }
  }, [costCentersData, isEditing])

  // Add new item
  const addItem = () => {
    const defaultCC = getDefaultCostCenter()
    setItems([...items, { 
      supplier: null, 
      current_balance: 0, 
      amount: 0,
      sultan_approval: 'جاري المعالجة',
      auditor_status: 'جاري المعالجة',
      financial_manager_approval: 'جاري المعالجة',
      proposed_amount: 0,
      abu_alaa_approval: 'جاري المعالجة',
      cost_center: defaultCC?.id,
      cost_center_name: defaultCC?.name
    }])
  }

  // Remove item
  const removeItem = (index: number) => {
    if (items.length > 1) {
      setItems(items.filter((_, i) => i !== index))
    }
  }

  // Update item
  const updateItem = (index: number, field: keyof PaymentItem, value: any) => {
    const newItems = [...items]
    newItems[index] = { ...newItems[index], [field]: value }
    setItems(newItems)
  }

  // Open supplier modal
  const openSupplierModal = (index: number) => {
    setSupplierModalIndex(index)
    setSupplierSearchQuery('')
    setSupplierModalOpen(true)
    setTimeout(() => searchInputRef.current?.focus(), 100)
  }

  // Select supplier from modal
  const selectSupplier = (supplier: any) => {
    if (supplierModalIndex === null) return
    const defaultCC = getDefaultCostCenter()
    const newItems = [...items]
    newItems[supplierModalIndex] = {
      ...newItems[supplierModalIndex],
      supplier: supplier.id,
      supplier_name: supplier.name,
      cost_center: defaultCC?.id,
      cost_center_name: defaultCC?.name
    }
    setItems(newItems)
    setSupplierModalOpen(false)
    setSupplierModalIndex(null)
    setSupplierSearchQuery('')
  }

  // Filtered suppliers for modal
  const getFilteredSuppliers = () => {
    const search = supplierSearchQuery.toLowerCase().trim()
    if (!search) return allSuppliers.slice(0, 50) // عرض أول 50 فقط بدون بحث
    return allSuppliers.filter(s =>
      s.name.toLowerCase().includes(search) ||
      s.code?.toLowerCase().includes(search)
    ).slice(0, 100) // عرض 100 نتيجة كحد أقصى
  }

  // Calculate totals
  const totalAmount = items.reduce((sum, item) => sum + (item.amount || 0), 0)
  const totalProposed = items.reduce((sum, item) => sum + (item.proposed_amount || 0), 0)

  // Submit form
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!branch) {
      toast.error('يرجى اختيار الفرع')
      return
    }

    if (items.some(item => !item.supplier)) {
      toast.error('يرجى اختيار المورد لجميع البنود')
      return
    }

    const payload = {
      branch,
      bank: bank || undefined,
      bank_account_number: bankAccountNumber,
      analytical_account: analyticalAccount,
      supplier_account: supplierAccountNumber,
      cost_center: costCenter || undefined,
      notes,
      items: items.map(item => ({
        supplier: item.supplier,
        current_balance: item.current_balance,
        amount: item.amount,
        proposed_amount: item.proposed_amount,
      }))
    }

    try {
      if (isEditing) {
        await updatePayment({ id: Number(id), data: payload }).unwrap()
        toast.success('تم تحديث الطلب بنجاح')
      } else {
        await createPayment(payload).unwrap()
        toast.success('تم إنشاء الطلب بنجاح')
      }
      navigate('/payments')
    } catch (error) {
      toast.error('حدث خطأ أثناء الحفظ')
      console.error(error)
    }
  }

  if (paymentLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/payments')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowRight className="w-5 h-5" />
          </button>
          <h1 className="text-2xl font-bold text-gray-900">
            {isEditing ? `تعديل طلب الدفع #${id}` : 'طلب دفع جديد'}
          </h1>
        </div>
        <Button onClick={handleSubmit} disabled={creating || updating}>
          <Save className="w-4 h-4 ml-2" />
          {creating || updating ? 'جاري الحفظ...' : 'حفظ الطلب'}
        </Button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Main Info */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-4">معلومات الطلب</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                الفرع <span className="text-red-500">*</span>
              </label>
              <select
                value={branch || ''}
                onChange={(e) => {
                  const branchId = e.target.value ? Number(e.target.value) : null
                  setBranch(branchId)
                  
                  // Auto-fill bank and cost center when branch is selected
                  if (branchId && branchesData?.results) {
                    const selectedBranch = branchesData.results.find(b => b.id === branchId)
                    if (selectedBranch) {
                      // Auto-set cost center from branch
                      if (selectedBranch.cost_center) {
                        setCostCenter(selectedBranch.cost_center)
                      }
                      
                      // Auto-set bank that belongs to this branch
                      if (banksData?.results) {
                        const branchBank = banksData.results.find((b: any) => b.branch === branchId)
                        if (branchBank) {
                          setBank(branchBank.id)
                          if (branchBank.account_number) {
                            setBankAccountNumber(branchBank.account_number)
                          }
                          if (branchBank.analytical_number) {
                            setAnalyticalAccount(branchBank.analytical_number)
                          }
                        }
                      }
                    }
                  } else {
                    // Clear if no branch selected
                    setBank(null)
                    setCostCenter(null)
                    setBankAccountNumber('')
                    setAnalyticalAccount('')
                  }
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                required
              >
                <option value="">اختر الفرع</option>
                {branchesData?.results?.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                البنك المحول منه
              </label>
              <select
                value={bank || ''}
                onChange={(e) => setBank(e.target.value ? Number(e.target.value) : null)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">اختر البنك</option>
                {banksData?.results?.map((b: any) => (
                  <option key={b.id} value={b.id}>{b.name} - {b.branch_name} ({b.code})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                رقم حساب البنك
              </label>
              <Input
                value={bankAccountNumber}
                onChange={(e) => setBankAccountNumber(e.target.value)}
                placeholder="أدخل رقم حساب البنك"
                className="w-full"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                الحساب التحليلي
              </label>
              <Input
                value={analyticalAccount}
                onChange={(e) => setAnalyticalAccount(e.target.value)}
                placeholder="أدخل الحساب التحليلي"
                className="w-full"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                رقم حساب المورد
              </label>
              <Input
                value={supplierAccountNumber}
                onChange={(e) => setSupplierAccountNumber(e.target.value)}
                placeholder="أدخل رقم حساب المورد"
                className="w-full"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                مركز التكلفة
              </label>
              <select
                value={costCenter || ''}
                onChange={(e) => setCostCenter(e.target.value ? Number(e.target.value) : null)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">اختر مركز التكلفة</option>
                {costCentersData?.results?.map((c: any) => (
                  <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                ملاحظات
              </label>
              <Input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="ملاحظات إضافية"
                className="w-full"
              />
            </div>
          </div>
        </Card>

        {/* Items */}
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">بنود الدفع ({items.length} بند)</h2>
            <Button type="button" variant="outline" size="sm" onClick={addItem}>
              <Plus className="w-4 h-4 ml-1" />
              إضافة بند
            </Button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">#</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">رقم المورد</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">اسم المورد</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">رصيد المورد</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">دفعة المشتريات</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">اعتماد سلطان</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">حالة المدقق</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">المدير المالي</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">اقتراح السداد</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">اعتماد أبو علاء</th>
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {items.map((item, index) => (
                  <tr key={index} className="hover:bg-gray-50">
                    <td className="px-3 py-3 text-sm text-gray-600">{index + 1}</td>
                    <td className="px-3 py-3">
                      <div className="text-sm text-gray-600 w-20 text-center">
                        {item.supplier || '-'}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <button
                        type="button"
                        onClick={() => openSupplierModal(index)}
                        className="flex items-center gap-2 w-44 px-3 py-2 border border-gray-300 rounded-lg hover:border-primary-500 hover:bg-primary-50 transition-colors text-right"
                      >
                        <Search className="w-4 h-4 text-gray-400 shrink-0" />
                        <span className={`flex-1 text-sm truncate ${item.supplier_name ? 'text-gray-900' : 'text-gray-400'}`}>
                          {item.supplier_name || 'اختر المورد...'}
                        </span>
                      </button>
                    </td>
                    <td className="px-3 py-3">
                      <input
                        type="text"
                        inputMode="numeric"
                        value={item.current_balance || ''}
                        onChange={(e) => updateItem(index, 'current_balance', Number(e.target.value) || 0)}
                        onFocus={(e) => e.target.value === '0' && (e.target.value = '')}
                        className="w-28 px-3 py-2 border border-gray-300 rounded-lg text-sm text-left focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <input
                        type="text"
                        inputMode="numeric"
                        value={item.amount || ''}
                        onChange={(e) => updateItem(index, 'amount', Number(e.target.value) || 0)}
                        onFocus={(e) => e.target.value === '0' && (e.target.value = '')}
                        className="w-28 px-3 py-2 border border-gray-300 rounded-lg text-sm text-left focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <select
                        value={item.sultan_approval}
                        onChange={(e) => updateItem(index, 'sultan_approval', e.target.value)}
                        className="w-28 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="جاري المعالجة">جاري المعالجة</option>
                        <option value="معتمد">معتمد</option>
                        <option value="مرفوض">مرفوض</option>
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <select
                        value={item.auditor_status}
                        onChange={(e) => updateItem(index, 'auditor_status', e.target.value)}
                        className="w-28 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="جاري المعالجة">جاري المعالجة</option>
                        <option value="معتمد">معتمد</option>
                        <option value="مرفوض">مرفوض</option>
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <select
                        value={item.financial_manager_approval}
                        onChange={(e) => updateItem(index, 'financial_manager_approval', e.target.value)}
                        className="w-28 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="جاري المعالجة">جاري المعالجة</option>
                        <option value="معتمد">معتمد</option>
                        <option value="مرفوض">مرفوض</option>
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <input
                        type="text"
                        inputMode="numeric"
                        value={item.proposed_amount || ''}
                        onChange={(e) => updateItem(index, 'proposed_amount', Number(e.target.value) || 0)}
                        onFocus={(e) => e.target.value === '0' && (e.target.value = '')}
                        className="w-28 px-3 py-2 border border-gray-300 rounded-lg text-sm text-left focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <select
                        value={item.abu_alaa_approval}
                        onChange={(e) => updateItem(index, 'abu_alaa_approval', e.target.value)}
                        className="w-28 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500"
                      >
                        <option value="جاري المعالجة">جاري المعالجة</option>
                        <option value="معتمد">معتمد</option>
                        <option value="مرفوض">مرفوض</option>
                      </select>
                    </td>
                    <td className="px-3 py-3">
                      <button
                        type="button"
                        onClick={() => removeItem(index)}
                        className="p-1 text-red-500 hover:bg-red-50 rounded"
                        disabled={items.length === 1}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-gray-100 font-semibold">
                  <td colSpan={3} className="px-3 py-3 text-right">الإجمالي ({items.length} بند)</td>
                  <td className="px-3 py-3 text-left">{totalAmount.toLocaleString()}</td>
                  <td className="px-3 py-3 text-left">{totalAmount.toLocaleString()}</td>
                  <td className="px-3 py-3"></td>
                  <td className="px-3 py-3"></td>
                  <td className="px-3 py-3"></td>
                  <td className="px-3 py-3 text-left">{totalProposed.toLocaleString()}</td>
                  <td className="px-3 py-3"></td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>
      </form>

      {/* Supplier Selection Modal */}
      {supplierModalOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          {/* Backdrop */}
          <div 
            className="fixed inset-0 bg-black/40 transition-opacity"
            onClick={() => setSupplierModalOpen(false)}
          />
          
          {/* Modal */}
          <div className="flex min-h-full items-center justify-center p-4">
            <div className="relative w-full max-w-md bg-white rounded-xl shadow-xl transform transition-all">
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b bg-primary-600 rounded-t-xl">
                <div className="flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-white" />
                  <h3 className="text-base font-semibold text-white">اختيار المورد</h3>
                </div>
                <button
                  onClick={() => setSupplierModalOpen(false)}
                  className="p-1 hover:bg-white/20 rounded-lg transition-colors"
                >
                  <X className="w-4 h-4 text-white" />
                </button>
              </div>

              {/* Search */}
              <div className="p-3 border-b">
                <div className="relative">
                  <Search className="w-4 h-4 text-gray-400 absolute right-3 top-1/2 -translate-y-1/2" />
                  <input
                    ref={searchInputRef}
                    type="text"
                    value={supplierSearchQuery}
                    onChange={(e) => setSupplierSearchQuery(e.target.value)}
                    placeholder="ابحث بالاسم أو الكود..."
                    className="w-full pr-10 pl-3 py-2 border border-gray-300 rounded-lg focus:border-primary-500 focus:ring-2 focus:ring-primary-100 transition-all text-sm"
                    autoFocus
                  />
                </div>
                <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
                  <span>الإجمالي: {allSuppliers.length.toLocaleString()}</span>
                  <span>النتائج: {getFilteredSuppliers().length}</span>
                </div>
              </div>

              {/* Results */}
              <div className="max-h-64 overflow-y-auto">
                {getFilteredSuppliers().length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-gray-500">
                    <Search className="w-8 h-8 text-gray-300 mb-2" />
                    <p className="text-sm font-medium">لا توجد نتائج</p>
                  </div>
                ) : (
                  <div className="divide-y">
                    {getFilteredSuppliers().map((supplier) => (
                      <button
                        key={supplier.id}
                        type="button"
                        onClick={() => selectSupplier(supplier)}
                        className={`w-full px-4 py-2.5 flex items-center gap-3 hover:bg-gray-50 transition-colors text-right ${
                          supplierModalIndex !== null && items[supplierModalIndex]?.supplier === supplier.id
                            ? 'bg-primary-50 border-r-2 border-primary-600'
                            : ''
                        }`}
                      >
                        <div className="w-8 h-8 bg-primary-100 rounded-lg flex items-center justify-center shrink-0">
                          <User className="w-4 h-4 text-primary-600" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-gray-900 text-sm truncate">{supplier.name}</div>
                          <div className="text-xs text-gray-500">
                            كود: {supplier.code}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="px-4 py-2.5 border-t bg-gray-50 rounded-b-xl">
                <button
                  type="button"
                  onClick={() => setSupplierModalOpen(false)}
                  className="w-full py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
                >
                  إلغاء
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
