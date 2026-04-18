import { useState } from 'react'
import { Plus, Edit, Trash2, Landmark, Search, Copy } from 'lucide-react'
import { Button, Card, Input } from '../components/ui'
import { useGetBanksQuery, useCreateBankMutation, useUpdateBankMutation, useDeleteBankMutation, useGetBranchesQuery } from '../store/api'
import toast from 'react-hot-toast'

export default function Banks() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [showModal, setShowModal] = useState(false)
  const [editingBank, setEditingBank] = useState<any>(null)
  const [formData, setFormData] = useState({ name: '', code: '', branch: 0, account_number: '', iban: '' })

  const { data, isLoading, refetch } = useGetBanksQuery({ page, search })
  const { data: branchesData } = useGetBranchesQuery({ page: 1 })
  const [createBank, { isLoading: creating }] = useCreateBankMutation()
  const [updateBank, { isLoading: updating }] = useUpdateBankMutation()
  const [deleteBank] = useDeleteBankMutation()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const submitData = { 
        name: formData.name, 
        code: formData.code, 
        branch: formData.branch || undefined, 
        account_number: formData.account_number, 
        iban: formData.iban 
      }
      if (editingBank) {
        await updateBank({ id: editingBank.id, data: submitData }).unwrap()
        toast.success('تم تحديث البنك بنجاح')
      } else {
        await createBank(submitData).unwrap()
        toast.success('تم إضافة البنك بنجاح')
      }
      setShowModal(false)
      setEditingBank(null)
      setFormData({ name: '', code: '', branch: 0, account_number: '', iban: '' })
      refetch()
    } catch (error) {
      toast.error('حدث خطأ')
    }
  }

  const handleEdit = (bank: any) => {
    setEditingBank(bank)
    setFormData({ 
      name: bank.name, 
      code: bank.code, 
      branch: bank.branch || 0, 
      account_number: bank.account_number || '', 
      iban: bank.iban || '' 
    })
    setShowModal(true)
  }

  const handleDelete = async (id: number) => {
    if (confirm('هل أنت متأكد من حذف هذا البنك؟')) {
      try {
        await deleteBank(id).unwrap()
        toast.success('تم حذف البنك')
        refetch()
      } catch (error) {
        toast.error('لا يمكن حذف البنك')
      }
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success('تم النسخ')
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">البنوك</h1>
          <p className="text-gray-500 mt-1">إدارة الحسابات البنكية ({data?.count || 0} حساب)</p>
        </div>
        <Button onClick={() => { setEditingBank(null); setFormData({ name: '', code: '', branch: 0, account_number: '', iban: '' }); setShowModal(true) }}>
          <Plus className="w-4 h-4 ml-2" />
          إضافة حساب بنكي
        </Button>
      </div>

      {/* Search */}
      <Card className="p-4">
        <div className="relative">
          <Search className="w-5 h-5 text-gray-400 absolute right-3 top-1/2 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            placeholder="بحث في البنوك..."
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
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">اسم البنك</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">الكود</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">الفرع</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">رقم الحساب</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">IBAN</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">الحالة</th>
                  <th className="px-6 py-3 text-right text-sm font-medium text-gray-700">إجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {data?.results?.map((bank: any, index: number) => (
                  <tr key={bank.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-600">{index + 1}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center">
                          <Landmark className="w-5 h-5 text-emerald-600" />
                        </div>
                        <span className="font-medium">{bank.name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm">{bank.code}</td>
                    <td className="px-6 py-4 text-sm">{bank.branch_name || '-'}</td>
                    <td className="px-6 py-4">
                      {bank.account_number ? (
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm">{bank.account_number}</span>
                          <button onClick={() => copyToClipboard(bank.account_number)} className="text-gray-400 hover:text-gray-600">
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ) : '-'}
                    </td>
                    <td className="px-6 py-4">
                      {bank.iban ? (
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs">{bank.iban}</span>
                          <button onClick={() => copyToClipboard(bank.iban)} className="text-gray-400 hover:text-gray-600">
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ) : '-'}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded-full text-xs ${bank.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                        {bank.is_active ? 'نشط' : 'غير نشط'}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <button onClick={() => handleEdit(bank)} className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg">
                          <Edit className="w-4 h-4" />
                        </button>
                        <button onClick={() => handleDelete(bank.id)} className="p-2 text-red-600 hover:bg-red-50 rounded-lg">
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
                <Landmark className="w-12 h-12 mx-auto text-gray-300 mb-3" />
                <p>لا توجد حسابات بنكية</p>
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
            <h3 className="text-lg font-bold mb-4">{editingBank ? 'تعديل الحساب البنكي' : 'إضافة حساب بنكي جديد'}</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">اسم البنك *</label>
                <Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} required />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">الكود *</label>
                <Input value={formData.code} onChange={(e) => setFormData({ ...formData, code: e.target.value })} required />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">الفرع</label>
                <select 
                  value={formData.branch} 
                  onChange={(e) => setFormData({ ...formData, branch: Number(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                >
                  <option value={0}>اختر الفرع</option>
                  {branchesData?.results?.map((branch: any) => (
                    <option key={branch.id} value={branch.id}>{branch.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">رقم الحساب</label>
                <Input value={formData.account_number} onChange={(e) => setFormData({ ...formData, account_number: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">IBAN</label>
                <Input value={formData.iban} onChange={(e) => setFormData({ ...formData, iban: e.target.value })} />
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
