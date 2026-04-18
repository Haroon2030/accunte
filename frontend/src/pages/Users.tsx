import { useState } from 'react'
import { Plus, Eye, Edit2, Trash2, Users as UsersIcon, Shield, Building2, CheckCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import { Card, CardContent, Button, Input, Badge, Modal } from '@/components/ui'
import {
  useGetUsersQuery,
  useCreateUserMutation,
  useUpdateUserMutation,
  useDeleteUserMutation,
  useGetRolesQuery,
  useGetAllBranchesQuery,
  User,
} from '@/store/api'

// Role type labels
const roleTypeLabels: Record<string, string> = {
  admin: 'مدير النظام',
  manager: 'مدير',
  auditor: 'مدقق',
  branch_employee: 'موظف فرع',
}

// Role type colors
const roleTypeColors: Record<string, string> = {
  admin: 'bg-purple-100 text-purple-700',
  manager: 'bg-blue-100 text-blue-700',
  auditor: 'bg-amber-100 text-amber-700',
  branch_employee: 'bg-green-100 text-green-700',
}

// Initial form state
const initialFormState = {
  username: '',
  email: '',
  first_name: '',
  last_name: '',
  password: '',
  role: null as number | null,
  branch: null as number | null,
  is_active: true,
}

export default function Users() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading, isError, error } = useGetUsersQuery({ page, search })
  const { data: roles = [] } = useGetRolesQuery()
  const { data: branches = [] } = useGetAllBranchesQuery()
  const [createUser, { isLoading: isCreating }] = useCreateUserMutation()
  const [updateUser, { isLoading: isUpdating }] = useUpdateUserMutation()
  const [deleteUser, { isLoading: isDeleting }] = useDeleteUserMutation()

  const [isFormOpen, setIsFormOpen] = useState(false)
  const [isViewOpen, setIsViewOpen] = useState(false)
  const [isDeleteOpen, setIsDeleteOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<User | null>(null)
  const [formData, setFormData] = useState(initialFormState)
  const [isEditMode, setIsEditMode] = useState(false)

  const users = data?.results || []

  // Get selected role type
  const selectedRoleType = roles.find(r => r.id === formData.role)?.role_type

  // Open form for adding new user
  const handleAdd = () => {
    setFormData(initialFormState)
    setIsEditMode(false)
    setIsFormOpen(true)
  }

  // Open form for editing user
  const handleEdit = (user: User) => {
    setSelectedUser(user)
    setFormData({
      username: user.username,
      email: user.email,
      first_name: user.first_name,
      last_name: user.last_name,
      password: '',
      role: user.profile?.role || null,
      branch: user.profile?.branch || null,
      is_active: user.is_active,
    })
    setIsEditMode(true)
    setIsFormOpen(true)
  }

  // Open view modal
  const handleView = (user: User) => {
    setSelectedUser(user)
    setIsViewOpen(true)
  }

  // Open delete confirmation
  const handleDeleteClick = (user: User) => {
    setSelectedUser(user)
    setIsDeleteOpen(true)
  }

  // Confirm delete
  const handleDelete = async () => {
    if (!selectedUser) return
    try {
      await deleteUser(selectedUser.id).unwrap()
      toast.success('تم حذف المستخدم بنجاح')
      setIsDeleteOpen(false)
      setSelectedUser(null)
    } catch (err) {
      toast.error('حدث خطأ أثناء حذف المستخدم')
      console.error('Delete error:', err)
    }
  }

  // Submit form (create or update)
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.username.trim()) {
      toast.error('يرجى إدخال اسم المستخدم')
      return
    }
    if (!isEditMode && !formData.password.trim()) {
      toast.error('يرجى إدخال كلمة المرور')
      return
    }
    try {
      const submitData: any = {
        email: formData.email,
        first_name: formData.first_name,
        last_name: formData.last_name,
        is_active: formData.is_active,
      }
      
      // Add role only if selected
      if (formData.role) {
        submitData.role = formData.role
      }
      
      // Add branch only if selected (optional)
      if (formData.branch) {
        submitData.branch = formData.branch
      }
      
      // Add password only if provided
      if (formData.password) {
        submitData.password = formData.password
      }

      if (isEditMode && selectedUser) {
        await updateUser({ id: selectedUser.id, data: submitData }).unwrap()
        toast.success('تم تحديث بيانات المستخدم بنجاح')
      } else {
        // Only include username for new users
        submitData.username = formData.username
        await createUser(submitData).unwrap()
        toast.success('تم إضافة المستخدم بنجاح')
      }
      setIsFormOpen(false)
      setFormData(initialFormState)
      setSelectedUser(null)
    } catch (err: any) {
      const errorMsg = err?.data?.username?.[0] || err?.data?.email?.[0] || 'حدث خطأ أثناء حفظ البيانات'
      toast.error(errorMsg)
      console.error('Submit error:', err)
    }
  }

  // Update form field
  const updateField = (field: string, value: string | boolean | number | null) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  // Format date
  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString('ar-SA')
  }

  // Get user display name
  const getUserDisplayName = (user: User) => {
    if (user.first_name && user.last_name) {
      return `${user.first_name} ${user.last_name}`
    }
    if (user.first_name) return user.first_name
    return user.username
  }

  // Stats
  const stats = {
    total: data?.count || 0,
    active: users.filter(u => u.is_active).length,
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
              <p className="text-sm text-gray-500">إجمالي المستخدمين</p>
              <p className="text-lg font-bold text-gray-900">{stats.total} مستخدم</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4">
            <div className="w-12 h-12 bg-success-100 rounded-xl flex items-center justify-center">
              <CheckCircle className="w-6 h-6 text-success-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">المستخدمين النشطين</p>
              <p className="text-lg font-bold text-gray-900">{stats.active} مستخدم</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search and Add */}
      <Card>
        <CardContent className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <Input
            type="search"
            placeholder="بحث عن مستخدم..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            searchMode
            className="w-full sm:w-80"
          />
          <Button onClick={handleAdd}>
            <Plus className="w-5 h-5" />
            <span className="mr-2">إضافة مستخدم</span>
          </Button>
        </CardContent>
      </Card>

      {/* Users Table */}
      <div className="modern-table-container">
        <div className="overflow-x-auto">
          <table className="modern-table">
            <thead>
              <tr>
                <th>#</th>
                <th>اسم المستخدم</th>
                <th>الاسم الكامل</th>
                <th>الدور</th>
                <th>الفرع</th>
                <th>الحالة</th>
                <th>إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="table-empty-state">
                      <UsersIcon className="icon" />
                      <p className="text">لا يوجد مستخدمين</p>
                    </div>
                  </td>
                </tr>
              ) : (
                users.map((user, index) => (
                  <tr key={user.id}>
                    <td>{(page - 1) * 8 + index + 1}</td>
                    <td><span className="code-text">{user.username}</span></td>
                    <td className="font-medium text-slate-800">{getUserDisplayName(user)}</td>
                    <td>
                      {user.profile?.role_type ? (
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${roleTypeColors[user.profile.role_type] || 'bg-gray-100 text-gray-700'}`}>
                          {user.profile.role_name || roleTypeLabels[user.profile.role_type] || user.profile.role_type}
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td>
                      {user.profile?.branch_name ? (
                        <span className="flex items-center gap-1 text-sm">
                          <Building2 className="w-4 h-4 text-gray-400" />
                          {user.profile.branch_name}
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td>
                      <span className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}>
                        {user.is_active ? 'نشط' : 'غير نشط'}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center justify-center gap-1">
                        <button
                          onClick={() => handleView(user)}
                          className="action-btn edit"
                          title="عرض"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleEdit(user)}
                          className="action-btn edit"
                          title="تعديل"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteClick(user)}
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

      {/* Add/Edit Form Modal */}
      <Modal
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        title={isEditMode ? 'تعديل بيانات المستخدم' : 'إضافة مستخدم جديد'}
        size="lg"
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="اسم المستخدم"
              value={formData.username}
              onChange={(e) => updateField('username', e.target.value)}
              placeholder="مثال: ahmed"
              required
              disabled={isEditMode}
            />
            <Input
              label="البريد الإلكتروني"
              type="email"
              value={formData.email}
              onChange={(e) => updateField('email', e.target.value)}
              placeholder="example@email.com"
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="الاسم الأول"
              value={formData.first_name}
              onChange={(e) => updateField('first_name', e.target.value)}
              placeholder="أحمد"
            />
            <Input
              label="الاسم الأخير"
              value={formData.last_name}
              onChange={(e) => updateField('last_name', e.target.value)}
              placeholder="محمد"
            />
          </div>
          <Input
            label={isEditMode ? "كلمة المرور الجديدة (اتركها فارغة للإبقاء على القديمة)" : "كلمة المرور"}
            type="password"
            value={formData.password}
            onChange={(e) => updateField('password', e.target.value)}
            placeholder="********"
            required={!isEditMode}
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">الدور</label>
              <select
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all text-gray-900"
                value={formData.role || ''}
                onChange={(e) => updateField('role', e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">-- اختر الدور --</option>
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name} ({roleTypeLabels[role.role_type] || role.role_type})
                  </option>
                ))}
              </select>
            </div>
            
            {/* Branch selector - always visible */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                الفرع
                {selectedRoleType === 'branch_employee' && <span className="text-danger-500 mr-1">*</span>}
              </label>
              <select
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all text-gray-900"
                value={formData.branch || ''}
                onChange={(e) => updateField('branch', e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">-- اختر الفرع --</option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.code} - {branch.name}
                  </option>
                ))}
              </select>
              {selectedRoleType === 'branch_employee' && (
                <p className="text-xs text-gray-500 mt-1">مطلوب لموظفي الفروع</p>
              )}
            </div>
          </div>
          
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
              <span className="ms-3 text-sm font-medium text-gray-700">مستخدم نشط</span>
            </label>
          </div>
        </form>
      </Modal>

      {/* View Modal */}
      <Modal
        isOpen={isViewOpen}
        onClose={() => setIsViewOpen(false)}
        title="تفاصيل المستخدم"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsViewOpen(false)}>
              إغلاق
            </Button>
            <Button
              onClick={() => {
                setIsViewOpen(false)
                if (selectedUser) handleEdit(selectedUser)
              }}
            >
              <Edit2 className="w-4 h-4" />
              <span className="mr-2">تعديل</span>
            </Button>
          </>
        }
      >
        {selectedUser && (
          <div className="space-y-6">
            <div className="flex items-center gap-4 pb-4 border-b">
              <div className="w-16 h-16 bg-primary-100 rounded-xl flex items-center justify-center">
                <UsersIcon className="w-8 h-8 text-primary-600" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">{getUserDisplayName(selectedUser)}</h3>
                <p className="font-mono text-primary-600">@{selectedUser.username}</p>
                <div className="mt-1">
                  {selectedUser.is_active ? (
                    <Badge variant="success" withDot>نشط</Badge>
                  ) : (
                    <Badge variant="gray" withDot>غير نشط</Badge>
                  )}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-purple-50 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Shield className="w-5 h-5 text-purple-600" />
                  <p className="text-sm text-purple-600">الدور</p>
                </div>
                <p className="text-lg font-bold text-purple-700">
                  {selectedUser.profile?.role_name || 'غير محدد'}
                </p>
                {selectedUser.profile?.role_type && (
                  <p className="text-sm text-purple-500">
                    {roleTypeLabels[selectedUser.profile.role_type] || selectedUser.profile.role_type}
                  </p>
                )}
              </div>
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Building2 className="w-5 h-5 text-blue-600" />
                  <p className="text-sm text-blue-600">الفرع</p>
                </div>
                <p className="text-lg font-bold text-blue-700">
                  {selectedUser.profile?.branch_name || 'غير محدد'}
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-500">البريد الإلكتروني</p>
                <p className="text-lg font-semibold">{selectedUser.email || '-'}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-500">تاريخ الإنشاء</p>
                <p className="text-lg font-semibold">{formatDate(selectedUser.date_joined)}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-500">آخر تسجيل دخول</p>
                <p className="text-lg font-semibold">{formatDate(selectedUser.last_login)}</p>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        title="حذف المستخدم"
        size="sm"
        showCloseButton={false}
      >
        <div className="text-center">
          <div className="mx-auto w-14 h-14 rounded-full flex items-center justify-center bg-danger-100 text-danger-600">
            <Trash2 className="w-7 h-7" />
          </div>
          <h3 className="mt-4 text-lg font-semibold text-gray-900">حذف المستخدم</h3>
          <p className="mt-2 text-gray-600">
            هل أنت متأكد من حذف "{selectedUser?.username}"؟ لا يمكن التراجع عن هذا الإجراء.
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
