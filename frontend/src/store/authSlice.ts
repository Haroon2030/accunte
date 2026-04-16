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

const initialState: AuthState = {
  user: null,
  tokens: null,
  isLoading: false,
}

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
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload
    },
    logout: (state) => {
      state.user = null
      state.tokens = null
    },
  },
})

export const { setCredentials, setLoading, logout } = authSlice.actions
export default authSlice.reducer
