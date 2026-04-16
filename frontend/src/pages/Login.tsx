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
      // Mock login for now
      await new Promise(resolve => setTimeout(resolve, 1000))
      dispatch(setCredentials({
        user: {
          id: 1,
          username,
          email: `${username}@sovereign.com`,
          first_name: 'أحمد',
          last_name: 'محمد',
          is_staff: true,
        },
        tokens: {
          access: 'mock-access-token',
          refresh: 'mock-refresh-token',
        },
      }))
      toast.success('تم تسجيل الدخول بنجاح')
      navigate('/')
    } catch {
      toast.error('خطأ في تسجيل الدخول')
    } finally {
      setIsLoadingState(false)
      dispatch(setLoading(false))
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-900 via-primary-800 to-primary-700 flex items-center justify-center p-4" dir="rtl">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-20 h-20 bg-white rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-xl">
            <Landmark className="w-12 h-12 text-primary-700" />
          </div>
          <h1 className="text-3xl font-bold text-white">Sovereign Logic</h1>
          <p className="text-primary-200 mt-2">نظام إدارة المدفوعات المالية</p>
        </div>

        <Card className="shadow-2xl">
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
                required
              />

              <div className="relative">
                <Input
                  label="كلمة المرور"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="أدخل كلمة المرور"
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

              <Button type="submit" className="w-full" isLoading={isLoading}>
                تسجيل الدخول
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="text-center mt-8">
          <p className="text-primary-200 text-sm">© 2024 Sovereign Logic. جميع الحقوق محفوظة</p>
        </div>
      </div>
    </div>
  )
}
