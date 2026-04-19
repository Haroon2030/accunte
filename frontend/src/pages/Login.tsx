import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { Landmark, Eye, EyeOff } from 'lucide-react'
import toast from 'react-hot-toast'
import { Button, Input, Card, CardContent } from '@/components/ui'
import { setCredentials, setLoading } from '@/store/authSlice'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoadingState] = useState(false)
  const navigate = useNavigate()
  const dispatch = useDispatch()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) {
      toast.error('يرجى إدخال اسم المستخدم وكلمة المرور')
      return
    }
    setIsLoadingState(true)
    dispatch(setLoading(true))
    
    try {
      // Get JWT tokens
      const tokenResponse = await fetch('/api/token/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      
      if (!tokenResponse.ok) {
        const errorData = await tokenResponse.json()
        throw new Error(errorData.detail || 'خطأ في تسجيل الدخول')
      }
      
      const tokens = await tokenResponse.json()
      
      // Get user info
      const userResponse = await fetch('/api/v1/me/', {
        headers: { 'Authorization': `Bearer ${tokens.access}` },
      })
      
      if (!userResponse.ok) {
        throw new Error('خطأ في جلب بيانات المستخدم')
      }
      
      const user = await userResponse.json()
      
      dispatch(setCredentials({
        user,
        tokens: {
          access: tokens.access,
          refresh: tokens.refresh,
        },
      }))
      toast.success('تم تسجيل الدخول بنجاح')
      navigate('/')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'خطأ في تسجيل الدخول')
    } finally {
      setIsLoadingState(false)
      dispatch(setLoading(false))
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-primary-50 flex items-center justify-center p-4" dir="rtl">
      {/* Background Pattern */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary-200 rounded-full opacity-20 blur-3xl"></div>
        <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-primary-300 rounded-full opacity-20 blur-3xl"></div>
      </div>

      <div className="w-full max-w-md relative z-10">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-20 h-20 bg-gradient-to-br from-primary-500 to-primary-700 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-primary-500/30">
            <Landmark className="w-12 h-12 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-gray-800">نظام المدفوعات</h1>
          <p className="text-gray-500 mt-2">نظام إدارة المدفوعات المالية</p>
        </div>

        <Card className="shadow-xl border-0 bg-white/80 backdrop-blur-sm">
          <CardContent className="p-8">
            <div className="text-center mb-6">
              <h2 className="text-xl font-bold text-gray-900">تسجيل الدخول</h2>
              <p className="text-gray-500 mt-1">أدخل بياناتك للوصول إلى حسابك</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <Input
                label="اسم المستخدم"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="أدخل اسم المستخدم"
                autoComplete="username"
                required
              />

              <div className="relative">
                <Input
                  label="كلمة المرور"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="أدخل كلمة المرور"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute left-3 top-9 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>

              <Button type="submit" className="w-full bg-gradient-to-l from-primary-600 to-primary-500 hover:from-primary-700 hover:to-primary-600 shadow-lg shadow-primary-500/30" isLoading={isLoading}>
                تسجيل الدخول
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="text-center mt-8">
          <p className="text-gray-500 text-sm">© 2024 نظام المدفوعات. جميع الحقوق محفوظة</p>
        </div>
      </div>
    </div>
  )
}
