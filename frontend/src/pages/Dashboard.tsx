import { 
  Building2, 
  Users, 
  Landmark, 
  CreditCard, 
  Clock, 
  CheckCircle2, 
  XCircle,
  TrendingUp,
  Calendar,
  RefreshCw
} from 'lucide-react'
import { Card, CardContent, Badge } from '@/components/ui'
import { useGetDashboardQuery } from '@/store/api'

export default function Dashboard() {
  const { data, isLoading, isError, refetch } = useGetDashboardQuery()

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat('ar-SA').format(num)
  }

  const formatCurrency = (num: number) => {
    return new Intl.NumberFormat('ar-SA', {
      style: 'decimal',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num) + ' ر.س'
  }

  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, { label: string; variant: 'warning' | 'primary' | 'success' | 'danger' | 'gray' }> = {
      draft: { label: 'مسودة', variant: 'gray' },
      proposed: { label: 'مقترح', variant: 'primary' },
      first_approved: { label: 'موافقة أولية', variant: 'warning' },
      audited: { label: 'مدقق', variant: 'primary' },
      final_approved: { label: 'معتمد', variant: 'success' },
      rejected: { label: 'مرفوض', variant: 'danger' },
    }
    const s = statusMap[status] || { label: status, variant: 'gray' as const }
    return <Badge variant={s.variant}>{s.label}</Badge>
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-96 text-center">
        <p className="text-danger-600 mb-4">حدث خطأ أثناء تحميل البيانات</p>
        <button 
          onClick={() => refetch()}
          className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          إعادة المحاولة
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">لوحة التحكم</h1>
          <p className="text-gray-500 mt-1">نظرة عامة على إدارة المدفوعات</p>
        </div>
        <button 
          onClick={() => refetch()}
          className="px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 flex items-center gap-2 text-gray-600"
        >
          <RefreshCw className="w-4 h-4" />
          تحديث
        </button>
      </div>

      {/* Main Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-gradient-to-br from-blue-500 to-blue-600 text-white border-0">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-blue-100 text-sm">الفروع</p>
                <p className="text-3xl font-bold mt-1">{data.branches_count}</p>
              </div>
              <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
                <Building2 className="w-6 h-6" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-emerald-500 to-emerald-600 text-white border-0">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-emerald-100 text-sm">الموردين</p>
                <p className="text-3xl font-bold mt-1">{data.suppliers_count}</p>
              </div>
              <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
                <Users className="w-6 h-6" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-violet-500 to-violet-600 text-white border-0">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-violet-100 text-sm">البنوك</p>
                <p className="text-3xl font-bold mt-1">{data.banks_count}</p>
              </div>
              <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
                <Landmark className="w-6 h-6" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-amber-500 to-amber-600 text-white border-0">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-amber-100 text-sm">إجمالي المدفوعات</p>
                <p className="text-2xl font-bold mt-1">{formatCurrency(data.total_payments)}</p>
              </div>
              <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
                <CreditCard className="w-6 h-6" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Payment Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 bg-amber-100 rounded-2xl flex items-center justify-center">
                <Clock className="w-7 h-7 text-amber-600" />
              </div>
              <div>
                <p className="text-gray-500 text-sm">قيد الانتظار</p>
                <p className="text-2xl font-bold text-gray-900">{data.pending_payments}</p>
                <p className="text-xs text-gray-400">طلب</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 bg-emerald-100 rounded-2xl flex items-center justify-center">
                <CheckCircle2 className="w-7 h-7 text-emerald-600" />
              </div>
              <div>
                <p className="text-gray-500 text-sm">معتمدة</p>
                <p className="text-2xl font-bold text-gray-900">{data.approved_payments}</p>
                <p className="text-xs text-gray-400">طلب</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 bg-red-100 rounded-2xl flex items-center justify-center">
                <XCircle className="w-7 h-7 text-red-600" />
              </div>
              <div>
                <p className="text-gray-500 text-sm">مرفوضة</p>
                <p className="text-2xl font-bold text-gray-900">{data.rejected_payments}</p>
                <p className="text-xs text-gray-400">طلب</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Today & Month Stats + Status Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Today & Month */}
        <div className="space-y-4">
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <Calendar className="w-5 h-5 text-primary-600" />
                <span className="font-semibold text-gray-700">إحصائيات اليوم</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-500">طلبات اليوم</span>
                <span className="text-2xl font-bold text-primary-600">{data.today_payments}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5">
              <div className="flex items-center gap-3 mb-3">
                <TrendingUp className="w-5 h-5 text-emerald-600" />
                <span className="font-semibold text-gray-700">هذا الشهر</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-500">إجمالي المدفوعات</span>
                <span className="text-xl font-bold text-emerald-600">{formatCurrency(data.this_month_total)}</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Status Distribution */}
        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <h3 className="font-semibold text-gray-800 mb-4">توزيع حالات الطلبات</h3>
            <div className="space-y-3">
              {data.status_distribution.map((item) => {
                const total = data.status_distribution.reduce((sum, i) => sum + i.count, 0) || 1
                const percentage = Math.round((item.count / total) * 100)
                return (
                  <div key={item.status} className="flex items-center gap-3">
                    <div className="w-24 text-sm text-gray-600">{item.label}</div>
                    <div className="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden">
                      <div 
                        className="h-full rounded-full transition-all duration-500"
                        style={{ 
                          width: `${percentage}%`,
                          backgroundColor: item.color
                        }}
                      />
                    </div>
                    <div className="w-12 text-left text-sm font-medium text-gray-700">{item.count}</div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Monthly Payments Chart */}
      {data.monthly_payments.length > 0 && (
        <Card>
          <CardContent className="p-5">
            <h3 className="font-semibold text-gray-800 mb-4">المدفوعات الشهرية (آخر 6 أشهر)</h3>
            <div className="flex items-end justify-between gap-2 h-48">
              {data.monthly_payments.map((month) => {
                const maxTotal = Math.max(...data.monthly_payments.map(m => m.total)) || 1
                const height = (month.total / maxTotal) * 100
                return (
                  <div key={month.month} className="flex-1 flex flex-col items-center">
                    <div className="text-xs text-gray-500 mb-1">{formatNumber(month.total)}</div>
                    <div 
                      className="w-full bg-gradient-to-t from-primary-500 to-primary-400 rounded-t-lg transition-all duration-500 hover:from-primary-600 hover:to-primary-500"
                      style={{ height: `${Math.max(height, 5)}%` }}
                    />
                    <div className="text-xs text-gray-500 mt-2 truncate w-full text-center">
                      {month.month.split('-')[1]}/{month.month.split('-')[0].slice(2)}
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Top Suppliers & Recent Payments */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Suppliers */}
        <Card>
          <CardContent className="p-5">
            <h3 className="font-semibold text-gray-800 mb-4">أفضل الموردين</h3>
            {data.top_suppliers.length === 0 ? (
              <p className="text-gray-500 text-center py-8">لا توجد بيانات</p>
            ) : (
              <div className="space-y-3">
                {data.top_suppliers.slice(0, 5).map((supplier, index) => (
                  <div key={supplier.code} className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-bold
                      ${index === 0 ? 'bg-amber-500' : index === 1 ? 'bg-gray-400' : index === 2 ? 'bg-amber-700' : 'bg-gray-300'}`}>
                      {index + 1}
                    </div>
                    <div className="flex-1">
                      <p className="font-medium text-gray-800">{supplier.name}</p>
                      <p className="text-xs text-gray-500">{supplier.count} طلب</p>
                    </div>
                    <div className="text-left">
                      <p className="font-semibold text-primary-600">{formatCurrency(supplier.total)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Payments */}
        <Card>
          <CardContent className="p-5">
            <h3 className="font-semibold text-gray-800 mb-4">آخر الطلبات</h3>
            {data.recent_payments.length === 0 ? (
              <p className="text-gray-500 text-center py-8">لا توجد طلبات</p>
            ) : (
              <div className="space-y-3">
                {data.recent_payments.slice(0, 5).map((payment) => (
                  <div key={payment.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl">
                    <div className="w-10 h-10 bg-primary-100 rounded-xl flex items-center justify-center">
                      <CreditCard className="w-5 h-5 text-primary-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-gray-800 truncate">
                        {payment.branch_name || 'طلب #' + payment.id}
                      </p>
                      <p className="text-xs text-gray-500">
                        {new Date(payment.created_at).toLocaleDateString('ar-SA')}
                      </p>
                    </div>
                    <div className="text-left">
                      {getStatusBadge(payment.status)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
