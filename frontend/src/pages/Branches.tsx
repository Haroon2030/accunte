import { useState } from 'react'
import { Plus, Edit, Trash2, Building2, Search } from 'lucide-react'
import { Button, Card, Input } from '../components/ui'
import { useGetBranchesQuery, useCreateBranchMutation, useUpdateBranchMutation, useDeleteBranchMutation, useGetCostCentersQuery } from '../store/api'
import toast from 'react-hot-toast'

export default function Branches() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [showModal, setShowModal] = useState(false)
  const [editingBranch, setEditingBranch] = useState<any>(null)
  const [formData, setFormData] = useState({ name: '', code: '', address: '', phone: '', cost_center: '' })

  const { data, isLoading, refetch } = useGetBranchesQuery({ page, search })
  const { data: costCentersData } = useGetCostCentersQuery({ page: 1, search: '' })
  const costCenters = costCentersData?.results || []
  const [createBranch, { isLoading: creating }] = useCreateBranchMutation()
  const [updateBranch, { isLoading: updating }] = useUpdateBranchMutation()
  const [deleteBranch] = useDeleteBranchMutation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const submitData = {
        ...formData,
        cost_center: formData.cost_center ? parseInt(formData.cost_center) : undefined
      }
      if (editingBranch) {
        await updateBranch({ id: editingBranch.id, data: submitData }).unwrap()
        toast.success('تم تحديث الفرع بنجاح')
      } else {
        await createBranch(submitData).unwrap()
        toast.success('تم إضافة الفرع بنجاح')
      }
      setShowModal(false)
      setEditingBranch(null)
      setFormData({ name: '', code: '', address: '', phone: '', cost_center: '' })
      refetch()
    } catch (error: any) {
      // Show specific error message
      const errorData = error?.data
      if (errorData?.code) {
        toast.error(`الكود: ${errorData.code[0]}`)
      } else if (errorData?.name) {
        toast.error(`الاسم: ${errorData.name[0]}`)
      } else if (errorData?.detail) {
        toast.error(errorData.detail)
      } else if (errorData?.non_field_errors) {
        toast.error(errorData.non_field_errors[0])
      } else {
        toast.error('حدث خطأ أثناء الحفظ')
      }
      console.error('Submit error:', error)
    }
  }

  const handleEdit = (branch: any) => {
    setEditingBranch(branch)
    setFormData({ name: branch.name, code: branch.code, address: branch.address || '', phone: branch.phone || '', cost_center: branch.cost_center?.toString() || '' })
    setShowModal(true)
  }

  const handleDelete = async (id: number) => {
    if (confirm('هل أنت متأكد من حذف هذا الفرع؟')) {
      try {
        await deleteBranch(id).unwrap()
        toast.success('تم حذف الفرع')
        refetch()
      } catch (error) {
        toast.error('لا يمكن حذف الفرع')
      }
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">الفروع</h1>
          <p className="text-gray-500 mt-1">إدارة فروع الشركة ({data?.count || 0} فرع)</p>
        </div>
        <Button onClick={() => { setEditingBranch(null); setFormData({ name: '', code: '', address: '', phone: '', cost_center: '' }); setShowModal(true) }}>
          <Plus className="w-4 h-4 ml-2" />
          إضافة فرع
        </Button>
      </div>

      {/* Search */}
      <Card className="p-4">
        <div className="relative">
          <Search className="w-5 h-5 text-gray-400 absolute right-3 top-1/2 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            placeholder="بحث في الفروع..."
            className="pr-10"
          />
        </div>
      </Card>

      {/* Table */}
      <div className="modern-table-container">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-10 w-10 border-4 border-primary-200 border-t-primary-600"></div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="modern-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>اسم الفرع</th>
                  <th>الكود</th>
                  <th>مركز التكلفة</th>
                  <th>عدد البنوك</th>
                  <th>الحالة</th>
                  <th>إجراءات</th>
                </tr>
              </thead>
              <tbody>
                {data?.results?.map((branch: any, index: number) => (
                  <tr key={branch.id}>
                    <td>{index + 1}</td>
                    <td className="font-medium text-slate-800">{branch.name}</td>
                    <td><span className="code-text">{branch.code}</span></td>
                    <td>{branch.cost_center_name || '-'}</td>
                    <td>{branch.banks_count || 0}</td>
                    <td>
                      <span className={`status-badge ${branch.is_active ? 'active' : 'inactive'}`}>
                        {branch.is_active ? 'نشط' : 'غير نشط'}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center justify-center gap-1">
                        <button onClick={() => handleEdit(branch)} className="action-btn edit">
                          <Edit className="w-4 h-4" />
                        </button>
                        <button onClick={() => handleDelete(branch.id)} className="action-btn delete">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(!data?.results || data.results.length === 0) && (
              <div className="table-empty-state">
                <Building2 className="icon" />
                <p className="text">لا توجد فروع</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Pagination */}
      {data && data.count > 0 && (
        <div className="modern-pagination">
          <Button variant="outline" size="sm" className="page-btn" disabled={!data.previous} onClick={() => setPage(p => p - 1)}>السابق</Button>
          <span className="page-info">صفحة {page} من {Math.ceil(data.count / 8)}</span>
          <Button variant="outline" size="sm" className="page-btn" disabled={!data.next} onClick={() => setPage(p => p + 1)}>التالي</Button>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="fixed inset-0 bg-black/50" onClick={() => setShowModal(false)} />
          <div className="relative bg-white rounded-xl shadow-xl w-full max-w-md p-6">
            <h3 className="text-lg font-bold mb-4">{editingBranch ? 'تعديل الفرع' : 'إضافة فرع جديد'}</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">اسم الفرع *</label>
                <Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} required />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">الكود *</label>
                <Input value={formData.code} onChange={(e) => setFormData({ ...formData, code: e.target.value })} required />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">مركز التكلفة </label>
                <select
                  value={formData.cost_center}
                  onChange={(e) => setFormData({ ...formData, cost_center: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                  <option value="">-- اختر مركز التكلفة --</option>
                  {costCenters.map((cc) => (
                    <option key={cc.id} value={cc.id}>{cc.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">العنوان</label>
                <Input value={formData.address} onChange={(e) => setFormData({ ...formData, address: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">الهاتف</label>
                <Input value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })} />
              </div>
              <div className="flex gap-3 pt-4">
                <Button type="submit" disabled={creating || updating} className="flex-1">
                  {creating || updating ? 'جاري الحفظ...' : 'حفظ'}
                </Button>
                <Button type="button" variant="outline" onClick={() => setShowModal(false)}>إلغاء</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
