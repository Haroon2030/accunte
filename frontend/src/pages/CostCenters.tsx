import { useState } from 'react'
import { Plus, Edit, Trash2, BarChart3, Search } from 'lucide-react'
import { Button, Card, Input } from '../components/ui'
import { useGetCostCentersQuery, useCreateCostCenterMutation, useUpdateCostCenterMutation, useDeleteCostCenterMutation } from '../store/api'
import toast from 'react-hot-toast'

export default function CostCenters() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [showModal, setShowModal] = useState(false)
  const [editingCenter, setEditingCenter] = useState<any>(null)
  const [formData, setFormData] = useState({ name: '', code: '', description: '' })

  const { data, isLoading, refetch } = useGetCostCentersQuery({ page, search })
  const [createCostCenter, { isLoading: creating }] = useCreateCostCenterMutation()
  const [updateCostCenter, { isLoading: updating }] = useUpdateCostCenterMutation()
  const [deleteCostCenter] = useDeleteCostCenterMutation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (editingCenter) {
        await updateCostCenter({ id: editingCenter.id, data: formData }).unwrap()
        toast.success('تم تحديث مركز التكلفة بنجاح')
      } else {
        await createCostCenter(formData).unwrap()
        toast.success('تم إضافة مركز التكلفة بنجاح')
      }
      setShowModal(false)
      setEditingCenter(null)
      setFormData({ name: '', code: '', description: '' })
      refetch()
    } catch (error) {
      toast.error('حدث خطأ')
    }
  }

  const handleEdit = (center: any) => {
    setEditingCenter(center)
    setFormData({ name: center.name, code: center.code, description: center.description || '' })
    setShowModal(true)
  }

  const handleDelete = async (id: number) => {
    if (confirm('هل أنت متأكد من حذف مركز التكلفة؟')) {
      try {
        await deleteCostCenter(id).unwrap()
        toast.success('تم حذف مركز التكلفة')
        refetch()
      } catch (error) {
        toast.error('لا يمكن حذف مركز التكلفة')
      }
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">مراكز التكلفة</h1>
          <p className="text-gray-500 mt-1">إدارة مراكز التكلفة ({data?.count || 0} مركز)</p>
        </div>
        <Button onClick={() => { setEditingCenter(null); setFormData({ name: '', code: '', description: '' }); setShowModal(true) }}>
          <Plus className="w-4 h-4 ml-2" />
          إضافة مركز تكلفة
        </Button>
      </div>

      {/* Search */}
      <Card className="p-4">
        <div className="relative">
          <Search className="w-5 h-5 text-gray-400 absolute right-3 top-1/2 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            placeholder="بحث في مراكز التكلفة..."
            className="pr-10"
          />
        </div>
      </Card>

      {/* Table */}
      <div className="modern-table-container">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-10 w-10 border-4 border-purple-200 border-t-purple-600"></div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="modern-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>اسم مركز التكلفة</th>
                  <th>الكود</th>
                  <th>عدد الفروع</th>
                  <th>الوصف</th>
                  <th>الحالة</th>
                  <th>إجراءات</th>
                </tr>
              </thead>
              <tbody>
                {data?.results?.map((center: any, index: number) => (
                  <tr key={center.id}>
                    <td>{index + 1}</td>
                    <td className="font-medium text-slate-800">{center.name}</td>
                    <td><span className="code-text">{center.code}</span></td>
                    <td>{center.branches_count || 0}</td>
                    <td className="max-w-xs truncate">{center.description || '-'}</td>
                    <td>
                      <span className={`status-badge ${center.is_active ? 'active' : 'inactive'}`}>
                        {center.is_active ? 'نشط' : 'غير نشط'}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center justify-center gap-1">
                        <button onClick={() => handleEdit(center)} className="action-btn edit">
                          <Edit className="w-4 h-4" />
                        </button>
                        <button onClick={() => handleDelete(center.id)} className="action-btn delete">
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
                <BarChart3 className="icon" />
                <p className="text">لا توجد مراكز تكلفة</p>
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
            <h3 className="text-lg font-bold mb-4">{editingCenter ? 'تعديل مركز التكلفة' : 'إضافة مركز تكلفة جديد'}</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">اسم مركز التكلفة *</label>
                <Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} required />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">الكود *</label>
                <Input value={formData.code} onChange={(e) => setFormData({ ...formData, code: e.target.value })} required />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">الوصف</label>
                <textarea 
                  value={formData.description} 
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 min-h-[80px]"
                />
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
