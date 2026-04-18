import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Plus, Trash2, Save, ArrowRight, Search, ChevronDown } from 'lucide-react'
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
  const [costCenter, setCostCenter] = useState<{ id: number; name: string } | null>(null)
  const [notes, setNotes] = useState('')
  const [items, setItems] = useState<PaymentItem[]>([
    { supplier: null, current_balance: 0, amount: 0, sultan_approval: 'جاري المعالجة', auditor_status: 'جاري المعالجة', financial_manager_approval: 'جاري المعالجة', proposed_amount: 0, abu_alaa_approval: 'جاري المعالجة' }
  ])
  const [supplierSearch, setSupplierSearch] = useState<Record<number, string>>({})
  const [activeSupplierDropdown, setActiveSupplierDropdown] = useState<number | null>(null)
  const dropdownRefs = useRef<Record<number, HTMLDivElement | null>>({})

  // Queries
  const { data: branchesData } = useGetBranchesQuery({ page: 1 })
  const { data: banksData } = useGetBanksQuery({ page: 1 })
  const { data: costCentersData } = useGetCostCentersQuery({ page: 1 })
  const { data: allSuppliers = [] } = useGetAllSuppliersQuery()
  const { data: paymentData, isLoading: paymentLoading } = useGetPaymentQuery(Number(id), { skip: !id })

  // Mutations
  const [createPayment, { isLoading: creating }] = useCreatePaymentMutation()
  const [updatePayment, { isLoading: updating }] = useUpdatePaymentMutation()

  // Auto-select cost center when branch changes
  useEffect(() => {
    if (branch && branchesData?.results) {
      const selectedBranch = branchesData.results.find(b => b.id === branch)
      if (selectedBranch && (selectedBranch as any).cost_center) {
        const ccId = (selectedBranch as any).cost_center
        const cc = costCentersData?.results?.find(c => c.id === ccId)
        if (cc) {
          setCostCenter({ id: cc.id, name: cc.name })
        }
      } else {
        setCostCenter(null)
      }
    }
  }, [branch, branchesData, costCentersData])

  // Load existing payment data
  useEffect(() => {
    if (paymentData && isEditing) {
      setBranch(paymentData.branch || null)
      setBank(paymentData.bank || null)
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

  // Select supplier
  const selectSupplier = (index: number, supplier: any) => {
    const defaultCC = getDefaultCostCenter()
    const newItems = [...items]
    newItems[index] = {
      ...newItems[index],
      supplier: supplier.id,
      supplier_name: supplier.name,
      cost_center: defaultCC?.id,
      cost_center_name: defaultCC?.name
    }
    setItems(newItems)
    setSupplierSearch(prev => ({ ...prev, [index]: '' }))
    setActiveSupplierDropdown(null)
  }

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (activeSupplierDropdown !== null) {
        const ref = dropdownRefs.current[activeSupplierDropdown]
        if (ref && !ref.contains(e.target as Node)) {
          setActiveSupplierDropdown(null)
        }
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [activeSupplierDropdown])

  // Filtered suppliers per row
  const getFilteredSuppliers = (index: number) => {
    const search = (supplierSearch[index] || '').toLowerCase()
    if (!search) return allSuppliers
    return allSuppliers.filter(s =>
      s.name.toLowerCase().includes(search) ||
      s.code?.toLowerCase().includes(search)
    )
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                الفرع <span className="text-red-500">*</span>
              </label>
              <select
                value={branch || ''}
                onChange={(e) => setBranch(e.target.value ? Number(e.target.value) : null)}
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
                {banksData?.results?.map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                مركز التكلفة <span className="text-xs text-blue-500">(تعبئة تلقائية)</span>
              </label>
              <div className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-700">
                {costCenter ? costCenter.name : 'يتم تحديده تلقائياً...'}
              </div>
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
                  <th className="px-3 py-3 text-right text-sm font-medium text-gray-700">الدفعة المرفوعة</th>
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
                      <Input
                        value={item.supplier || ''}
                        onChange={(e) => {
                          const val = e.target.value ? Number(e.target.value) : null
                          updateItem(index, 'supplier', val)
                          // Try to find supplier by id
                          if (val) {
                            const found = allSuppliers.find(s => s.id === val)
                            if (found) {
                              selectSupplier(index, found)
                            }
                          }
                        }}
                        placeholder="-"
                        className="w-20"
                      />
                    </td>
                    <td className="px-3 py-3 relative" ref={el => { dropdownRefs.current[index] = el }}>
                      <div className="relative">
                        <div 
                          className="flex items-center gap-1 cursor-pointer"
                          onClick={() => setActiveSupplierDropdown(activeSupplierDropdown === index ? null : index)}
                        >
                          <div className="relative flex-1">
                            <Input
                              value={item.supplier_name || ''}
                              readOnly
                              placeholder="اختر المورد..."
                              className="w-40 cursor-pointer pr-8 text-sm"
                            />
                            <Search className="w-4 h-4 text-gray-400 absolute right-2 top-1/2 -translate-y-1/2" />
                          </div>
                          <ChevronDown className={`w-4 h-4 text-gray-400 shrink-0 transition-transform ${activeSupplierDropdown === index ? 'rotate-180' : ''}`} />
                        </div>
                      </div>
                      {activeSupplierDropdown === index && (
                        <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-white border border-gray-300 rounded-lg shadow-lg overflow-hidden" style={{ width: '280px' }}>
                          {/* حقل البحث */}
                          <div className="sticky top-0 bg-white p-2 border-b">
                            <div className="relative">
                              <Input
                                value={supplierSearch[index] || ''}
                                onChange={(e) => setSupplierSearch(prev => ({ ...prev, [index]: e.target.value }))}
                                placeholder="ابحث بالاسم أو الكود..."
                                className="w-full pr-8"
                                autoFocus
                              />
                              <Search className="w-4 h-4 text-gray-400 absolute right-2 top-1/2 -translate-y-1/2" />
                            </div>
                            <div className="text-xs text-gray-500 mt-1 text-center">
                              {getFilteredSuppliers(index).length} مورد
                            </div>
                          </div>
                          {/* قائمة الموردين - 8 صفوف فقط */}
                          <div className="overflow-y-auto" style={{ maxHeight: '320px' }}>
                            {getFilteredSuppliers(index).length === 0 ? (
                              <div className="px-4 py-3 text-sm text-gray-500 text-center">لا توجد نتائج</div>
                            ) : (
                              getFilteredSuppliers(index).map((supplier) => (
                                <button
                                  key={supplier.id}
                                  type="button"
                                  onClick={() => selectSupplier(index, supplier)}
                                  className={`w-full px-4 py-2 text-right hover:bg-primary-50 border-b last:border-b-0 transition-colors ${
                                    item.supplier === supplier.id ? 'bg-primary-100 text-primary-700 font-medium' : ''
                                  }`}
                                >
                                  <div className="text-sm">{supplier.name}</div>
                                  <div className="text-xs text-gray-500">{supplier.code}</div>
                                </button>
                              ))
                            )}
                          </div>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <Input
                        type="number"
                        value={item.current_balance}
                        onChange={(e) => updateItem(index, 'current_balance', Number(e.target.value))}
                        className="w-24 text-left"
                      />
                    </td>
                    <td className="px-3 py-3">
                      <Input
                        type="number"
                        value={item.amount}
                        onChange={(e) => updateItem(index, 'amount', Number(e.target.value))}
                        className="w-24 text-left"
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
                      <Input
                        type="number"
                        value={item.proposed_amount}
                        onChange={(e) => updateItem(index, 'proposed_amount', Number(e.target.value))}
                        className="w-24 text-left"
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
    </div>
  )
}
