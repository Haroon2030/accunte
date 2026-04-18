import { useState } from 'react'
import { Plus, Eye, Edit2, Trash2, Users as UsersIcon, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { Card, CardContent, Button, Input, Badge, Modal } from '@/components/ui'
import {
  useGetSuppliersQuery,
  useCreateSupplierMutation,
  useUpdateSupplierMutation,
  useDeleteSupplierMutation,
  Supplier,
} from '@/store/api'

// Initial form state - only code and name fields
const initialFormState = {
  name: '',
  code: '',
  is_active: true,
}

export default function Suppliers() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading, isError, error } = useGetSuppliersQuery({ page, search })
  const [createSupplier, { isLoading: isCreating }] = useCreateSupplierMutation()
  const [updateSupplier, { isLoading: isUpdating }] = useUpdateSupplierMutation()
  const [deleteSupplier, { isLoading: isDeleting }] = useDeleteSupplierMutation()

  const [isFormOpen, setIsFormOpen] = useState(false)
  const [isViewOpen, setIsViewOpen] = useState(false)
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null)
  const [formData, setFormData] = useState(initialFormState)
  const [isEditMode, setIsEditMode] = useState(false)

  const suppliers = data?.results || []

  // Open form for adding new supplier
  const handleAdd = () => {
    setFormData(initialFormState)
    setIsEditMode(false)
    setIsFormOpen(true)
  }

  // Open form for editing supplier
  const handleEdit = (supplier: Supplier) => {
    setSelectedSupplier(supplier)
    setFormData({
      name: supplier.name,
      code: supplier.code,
      is_active: supplier.is_active,
    })
    setIsEditMode(true)
    setIsFormOpen(true)
  }

  // Open view modal
  const handleView = (supplier: Supplier) => {
    setSelectedSupplier(supplier)
    setIsViewOpen(true)
  }

  // Open delete confirmation
  const handleDeleteClick = (supplier: Supplier) => {
    setSelectedSupplier(supplier)
    setIsDeleteOpen(true)
  }

  // Confirm delete
  const handleDelete = async () => {
    if (!selectedSupplier) return
    try {
      await deleteSupplier(selectedSupplier.id).unwrap()
      toast.success('تم حذف المورد بنجاح')
      setIsDeleteOpen(false)
      setSelectedSupplier(null)
    } catch (err) {
      toast.error('حدث خطأ أثناء حذف المورد')
      console.error('Delete error:', err)
    }
  }

  // Submit form (create or update)
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.name.trim()) {
      toast.error('يرجى إدخال اسم المورد')
      return
    }
    try {
      if (isEditMode && selectedSupplier) {
        await updateSupplier({ id: selectedSupplier.id, data: formData }).unwrap()
        toast.success('تم تحديث بيانات المورد بنجاح')
      } else {
        await createSupplier(formData).unwrap()
        toast.success('تم إضافة المورد بنجاح')
      }
      setIsFormOpen(false)
      setFormData(initialFormState)
      setSelectedSupplier(null)
    } catch (err) {
      toast.error('حدث خطأ أثناء حفظ البيانات')
      console.error('Submit error:', err)
    }
  }

  // Update form field
  const updateField = (field: string, value: string | boolean) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  // Format number for display
  const formatNumber = (num: number | undefined) => {
    if (!num) return '0'
    return new Intl.NumberFormat('ar-SA').format(num)
  }

  // Stats
  const stats = {
    total: suppliers.length,
    active: suppliers.filter(s => s.is_active).length,
  }

  const isSaving = isCreating || isUpdating

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center min-h-96 text-center">
        <p className="text-danger-600 mb-4">حدث خطأ أثناء تحميل البيانات</p>
        <p className="text-gray-500 text-sm mb-4">{(error as any)?.message || 'يرجى المحاولة مرة أخرى'}</p>
        <Button onClick={() => window.location.reload()}>إعادة المحاولة</Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardContent className="flex items-center gap-4">
            <div className="w-12 h-12 bg-primary-100 rounded-xl flex items-center justify-center">
              <UsersIcon className="w-6 h-6 text-primary-700" />
            </div>
            <div>
              <p className="text-sm text-gray-500">إجمالي الموردين</p>
              <p className="text-lg font-bold text-gray-900">{stats.total} مورد</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4">
            <div className="w-12 h-12 bg-success-100 rounded-xl flex items-center justify-center">
              <CheckCircle className="w-6 h-6 text-success-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">الموردين النشطين</p>
              <p className="text-lg font-bold text-gray-900">{stats.active} مورد</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search and Add */}
      <Card>
        <CardContent className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <Input
            type="search"
            placeholder="بحث عن مورد..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            searchMode
            className="w-full sm:w-80"
          />
          <Button onClick={handleAdd}>
            <Plus className="w-5 h-5" />
            <span className="mr-2">إضافة مورد</span>
          </Button>
        </CardContent>
      </Card>

      {/* Suppliers Table */}
      <div className="modern-table-container">
          <div className="overflow-x-auto">
            <table className="modern-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>الكود</th>
                  <th>اسم المورد</th>
                  <th>الحالة</th>
                  <th>إجراءات</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.length === 0 ? (
                  <tr>
                    <td colSpan={5}>
                      <div className="table-empty-state">
                        <UsersIcon className="icon" />
                        <p className="text">لا يوجد موردين</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  suppliers.map((supplier, index) => (
                    <tr key={supplier.id}>
                      <td>{(page - 1) * 8 + index + 1}</td>
                      <td><span className="code-text">{supplier.code}</span></td>
                      <td className="font-medium text-slate-800">{supplier.name}</td>
                      <td>
                        <span className={`status-badge ${supplier.is_active ? 'active' : 'inactive'}`}>
                          {supplier.is_active ? 'نشط' : 'غير نشط'}
                        </span>
                      </td>
                      <td>
                        <div className="flex items-center justify-center gap-1">
                          <button
                            onClick={() => handleView(supplier)}
                            className="action-btn edit"
                            title="عرض"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleEdit(supplier)}
                            className="action-btn edit"
                            title="تعديل"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDeleteClick(supplier)}
                            className="action-btn delete"
                            title="حذف"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
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
      {data && data.count > 0 && (
        <div className="modern-pagination">
          <Button variant="outline" size="sm" className="page-btn" disabled={!data.previous} onClick={() => setPage(p => p - 1)}>السابق</Button>
          <span className="page-info">صفحة {page} من {Math.ceil(data.count / 8)}</span>
          <Button variant="outline" size="sm" className="page-btn" disabled={!data.next} onClick={() => setPage(p => p + 1)}>التالي</Button>
        </div>
      )}

      {/* Add/Edit Form Modal - SIMPLIFIED: Only code and name */}
      <Modal
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        title={isEditMode ? 'تعديل بيانات المورد' : 'إضافة مورد جديد'}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsFormOpen(false)}>
              إلغاء
            </Button>
            <Button onClick={handleSubmit} isLoading={isSaving}>
              {isEditMode ? 'حفظ التغييرات' : 'إضافة'}
            </Button>
          </>
        }
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Only two fields: name and code */}
          <Input
            label="رمز المورد"
            value={formData.code}
            onChange={(e) => updateField('code', e.target.value)}
            placeholder="مثال: SUP-001"
            disabled={isEditMode}
          />
          <Input
            label="اسم المورد"
            value={formData.name}
            onChange={(e) => updateField('name', e.target.value)}
            placeholder="اسم الشركة أو المؤسسة"
            required
          />
          
          {/* Active status toggle */}
          <div className="flex items-center gap-3 pt-2">
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={formData.is_active}
                onChange={(e) => updateField('is_active', e.target.checked)}
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-success-600" />
              <span className="ms-3 text-sm font-medium text-gray-700">مورد نشط</span>
            </label>
          </div>
        </form>
      </Modal>

      {/* View Modal */}
      <Modal
        isOpen={isViewOpen}
        onClose={() => setIsViewOpen(false)}
        title="تفاصيل المورد"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsViewOpen(false)}>
              إغلاق
            </Button>
            <Button
              onClick={() => {
                setIsViewOpen(false)
                if (selectedSupplier) handleEdit(selectedSupplier)
              }}
            >
              <Edit2 className="w-4 h-4" />
              <span className="mr-2">تعديل</span>
            </Button>
          </>
        }
      >
        {selectedSupplier && (
          <div className="space-y-6">
            <div className="flex items-center gap-4 pb-4 border-b">
              <div className="w-16 h-16 bg-primary-100 rounded-xl flex items-center justify-center">
                <UsersIcon className="w-8 h-8 text-primary-600" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">{selectedSupplier.name}</h3>
                <p className="font-mono text-primary-600">{selectedSupplier.code}</p>
                <div className="mt-1">
                  {selectedSupplier.is_active ? (
                    <Badge variant="success" withDot>نشط</Badge>
                  ) : (
                    <Badge variant="gray" withDot>غير نشط</Badge>
                  )}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-primary-50 rounded-lg p-4">
                <p className="text-sm text-primary-600">عدد الطلبات</p>
                <p className="text-2xl font-bold text-primary-700">
                  {selectedSupplier.payments_count || 0}
                </p>
              </div>
              <div className="bg-success-50 rounded-lg p-4">
                <p className="text-sm text-success-600">إجمالي المدفوعات</p>
                <p className="text-2xl font-bold text-success-700">
                  {formatNumber(selectedSupplier.total_payments)}
                </p>
              </div>
            </div>

            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-sm text-gray-500">تاريخ الإنشاء</p>
              <p className="text-lg font-semibold">
                {new Date(selectedSupplier.created_at).toLocaleDateString('ar-SA')}
              </p>
            </div>
          </div>
        )}
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        title="حذف المورد"
        size="sm"
        showCloseButton={false}
      >
        <div className="text-center">
          <div className="mx-auto w-14 h-14 rounded-full flex items-center justify-center bg-danger-100 text-danger-600">
            <Trash2 className="w-7 h-7" />
          </div>
          <h3 className="mt-4 text-lg font-semibold text-gray-900">حذف المورد</h3>
          <p className="mt-2 text-gray-600">
            هل أنت متأكد من حذف "{selectedSupplier?.name}"؟ لا يمكن التراجع عن هذا الإجراء.
          </p>
          <div className="mt-6 flex items-center justify-center gap-3">
            <Button variant="secondary" onClick={() => setIsDeleteOpen(false)} disabled={isDeleting}>
              إلغاء
            </Button>
            <Button variant="danger" onClick={handleDelete} isLoading={isDeleting}>
              حذف
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
