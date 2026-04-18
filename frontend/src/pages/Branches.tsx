import { useState } from 'react'
import { Plus, Edit, Trash2, Building2, Search } from 'lucide-react'
import { Button, Card, Input } from '../components/ui'
import { useGetBranchesQuery, useCreateBranchMutation, useUpdateBranchMutation, useDeleteBranchMutation } from '../store/api'
import toast from 'react-hot-toast'

export default function Branches() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [showModal, setShowModal] = useState(false)
  const [editingBranch, setEditingBranch] = useState<any>(null)
  const [formData, setFormData] = useState({ name: '', code: '', address: '', phone: '' })

  const { data, isLoading, refetch } = useGetBranchesQuery({ page, search })
  const [createBranch, { isLoading: creating }] = useCreateBranchMutation()
  const [updateBranch, { isLoading: updating }] = useUpdateBranchMutation()
  const [deleteBranch] = useDeleteBranchMutation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (editingBranch) {
        await updateBranch({ id: editingBranch.id, data: formData }).unwrap()
        toast.success('تم تحديث الفرع بنجاح')
      } else {
        await createBranch(formData).unwrap()
        toast.success('تم إضافة الفرع بنجاح')
      }
      setShowModal(false)
      setEditingBranch(null)
      setFormData({ name: '', code: '', address: '', phone: '' })
      refetch()
    } catch (error) {
      toast.error('حدث خطأ')
    }
  }

  const handleEdit = (branch: any) => {
    setEditingBranch(branch)
    setFormData({ name: branch.name, code: branch.code, address: branch.address || '', phone: branch.phone || '' })
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
        <Button onClick={() => { setEditingBranch(null); setFormData({ name: '', code: '', address: '', phone: '' }); setShowModal(true) }}>
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
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">#</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">اسم الفرع</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">الكود</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">مركز التكلفة</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">عدد البنوك</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">الحالة</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">إجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {data?.results?.map((branch: any, index: number) => (
                  <tr key={branch.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-600">{index + 1}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center">
                          <Building2 className="w-5 h-5 text-primary-600" />
                        </div>
                        <span className="font-medium">{branch.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm">{branch.code}</td>
                    <td className="px-6 py-4 text-sm">{branch.cost_center_name || '-'}</td>
                    <td className="px-6 py-4 text-sm">{branch.banks_count || 0}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded-full text-xs ${branch.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                        {branch.is_active ? 'نشط' : 'غير نشط'}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <button onClick={() => handleEdit(branch)} className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg">
                          <Edit className="w-4 h-4" />
                        </button>
                        <button onClick={() => handleDelete(branch.id)} className="p-2 text-red-600 hover:bg-red-50 rounded-lg">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(!data?.results || data.results.length === 0) && (
              <div className="text-center py-12 text-gray-500">
                <Building2 className="w-12 h-12 mx-auto text-gray-300 mb-3" />
                <p>لا توجد فروع</p>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Pagination */}
      {data && data.count > 10 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={!data.previous} onClick={() => setPage(p => p - 1)}>السابق</Button>
          <span className="text-sm text-gray-600">صفحة {page}</span>
          <Button variant="outline" size="sm" disabled={!data.next} onClick={() => setPage(p => p + 1)}>التالي</Button>
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
