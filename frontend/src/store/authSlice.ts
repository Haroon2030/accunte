import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface User {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  is_staff: boolean
}

interface AuthState {
  user: User | null
  tokens: {
    access: string
    refresh: string
  } | null
  isLoading: boolean
}

// Load initial state from localStorage
const loadFromStorage = (): AuthState => {
  try {
    const tokens = localStorage.getItem('tokens')
    const user = localStorage.getItem('user')
    return {
      tokens: tokens ? JSON.parse(tokens) : null,
      user: user ? JSON.parse(user) : null,
      isLoading: false,
    }
  } catch {
    return {
      user: null,
      tokens: null,
      isLoading: false,
    }
  }
}

const initialState: AuthState = loadFromStorage()

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    setCredentials: (
      state,
      action: PayloadAction<{ user: User; tokens: { access: string; refresh: string } }>
    ) => {
      state.user = action.payload.user
      state.tokens = action.payload.tokens
      // Save to localStorage
      localStorage.setItem('tokens', JSON.stringify(action.payload.tokens))
      localStorage.setItem('user', JSON.stringify(action.payload.user))
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload
    },
    logout: (state) => {
      state.user = null
      state.tokens = null
      // Clear localStorage
      localStorage.removeItem('tokens')
      localStorage.removeItem('user')
    },
  },
})

export const { setCredentials, setLoading, logout } = authSlice.actions
export default authSlice.reducer
