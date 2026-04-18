import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

// Define auth state type locally to avoid circular dependency
interface AuthState {
  tokens: {
    access: string
    refresh: string
  } | null
}

const baseQuery = fetchBaseQuery({
  baseUrl: '/api/v1',
  prepareHeaders: (headers, { getState }) => {
    const state = getState() as { auth: AuthState }
    const token = state.auth.tokens?.access
    if (token) {
      headers.set('authorization', `Bearer ${token}`)
    }
    return headers
  },
})

export const api = createApi({
  reducerPath: 'api',
  baseQuery,
  tagTypes: ['Suppliers', 'Branches', 'Banks', 'CostCenters', 'Payments', 'Users', 'Roles'],
  endpoints: (builder) => ({
    // Suppliers
    getSuppliers: builder.query<{ results: Supplier[]; count: number; next: string | null; previous: string | null }, { page?: number; search?: string; page_size?: number }>({
      query: ({ page = 1, search, page_size }) => ({
        url: '/suppliers/',
        params: { page, search, page_size },
      }),
      providesTags: ['Suppliers'],
    }),
    getAllSuppliers: builder.query<Supplier[], void>({
      query: () => '/suppliers/all/',
      providesTags: ['Suppliers'],
    }),
    createSupplier: builder.mutation<Supplier, Partial<Supplier>>({
      query: (data) => ({
        url: '/suppliers/',
        method: 'POST',
        body: data,
      }),
      invalidatesTags: ['Suppliers'],
    }),
    updateSupplier: builder.mutation<Supplier, { id: number; data: Partial<Supplier> }>({
      query: ({ id, data }) => ({
        url: `/suppliers/${id}/`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: ['Suppliers'],
    }),
    deleteSupplier: builder.mutation<void, number>({
      query: (id) => ({
        url: `/suppliers/${id}/`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Suppliers'],
    }),

    // Branches
    getBranches: builder.query<{ results: Branch[]; count: number; next?: string | null; previous?: string | null }, { page?: number; search?: string }>({
      query: ({ page = 1, search }) => ({
        url: '/branches/',
        params: { page, search },
      }),
      providesTags: ['Branches'],
    }),
    createBranch: builder.mutation<Branch, Partial<Branch>>({
      query: (data) => ({
        url: '/branches/',
        method: 'POST',
        body: data,
      }),
      invalidatesTags: ['Branches'],
    }),
    updateBranch: builder.mutation<Branch, { id: number; data: Partial<Branch> }>({
      query: ({ id, data }) => ({
        url: `/branches/${id}/`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: ['Branches'],
    }),
    deleteBranch: builder.mutation<void, number>({
      query: (id) => ({
        url: `/branches/${id}/`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Branches'],
    }),

    // Banks
    getBanks: builder.query<{ results: Bank[]; count: number; next?: string | null; previous?: string | null }, { page?: number; search?: string; page_size?: number }>({
      query: ({ page = 1, search, page_size }) => ({
        url: '/banks/',
        params: { page, search, page_size },
      }),
      providesTags: ['Banks'],
    }),
    createBank: builder.mutation<Bank, Partial<Bank>>({
      query: (data) => ({
        url: '/banks/',
        method: 'POST',
        body: data,
      }),
      invalidatesTags: ['Banks'],
    }),
    updateBank: builder.mutation<Bank, { id: number; data: Partial<Bank> }>({
      query: ({ id, data }) => ({
        url: `/banks/${id}/`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: ['Banks'],
    }),
    deleteBank: builder.mutation<void, number>({
      query: (id) => ({
        url: `/banks/${id}/`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Banks'],
    }),

    // Cost Centers
    getCostCenters: builder.query<{ results: CostCenter[]; count: number; next?: string | null; previous?: string | null }, { page?: number; search?: string; page_size?: number }>({
      query: ({ page = 1, search, page_size }) => ({
        url: '/cost-centers/',
        params: { page, search, page_size },
      }),
      providesTags: ['CostCenters'],
    }),
    createCostCenter: builder.mutation<CostCenter, Partial<CostCenter>>({
      query: (data) => ({
        url: '/cost-centers/',
        method: 'POST',
        body: data,
      }),
      invalidatesTags: ['CostCenters'],
    }),
    updateCostCenter: builder.mutation<CostCenter, { id: number; data: Partial<CostCenter> }>({
      query: ({ id, data }) => ({
        url: `/cost-centers/${id}/`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: ['CostCenters'],
    }),
    deleteCostCenter: builder.mutation<void, number>({
      query: (id) => ({
        url: `/cost-centers/${id}/`,
        method: 'DELETE',
      }),
      invalidatesTags: ['CostCenters'],
    }),

    // Payments
    getPayments: builder.query<{ results: PaymentRequest[]; count: number }, { page?: number; status?: string; branch?: number }>({
      query: ({ page = 1, status, branch }) => ({
        url: '/payments/',
        params: { page, status, branch },
      }),
      providesTags: ['Payments'],
    }),
    getPayment: builder.query<PaymentRequest, number>({
      query: (id) => `/payments/${id}/`,
      providesTags: ['Payments'],
    }),
    createPayment: builder.mutation<PaymentRequest, any>({
      query: (data) => ({
        url: '/payments/',
        method: 'POST',
        body: data,
      }),
      invalidatesTags: ['Payments'],
    }),
    updatePayment: builder.mutation<PaymentRequest, { id: number; data: any }>({
      query: ({ id, data }) => ({
        url: `/payments/${id}/`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: ['Payments'],
    }),
    deletePayment: builder.mutation<void, number>({
      query: (id) => ({
        url: `/payments/${id}/`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Payments'],
    }),
    
    // Dashboard
    getDashboard: builder.query<DashboardStats, void>({
      query: () => '/dashboard/',
      providesTags: ['Payments', 'Branches', 'Suppliers', 'Banks'],
    }),

    // Users
    getUsers: builder.query<{ results: User[]; count: number; next: string | null; previous: string | null }, { page?: number; search?: string }>({
      query: ({ page = 1, search }) => ({
        url: '/users/',
        params: { page, search },
      }),
      providesTags: ['Users'],
    }),
    createUser: builder.mutation<User, Partial<User> & { password?: string; role?: number; branch?: number }>({
      query: (data) => ({
        url: '/users/',
        method: 'POST',
        body: data,
      }),
      invalidatesTags: ['Users'],
    }),
    updateUser: builder.mutation<User, { id: number; data: Partial<User> & { password?: string; role?: number; branch?: number } }>({
      query: ({ id, data }) => ({
        url: `/users/${id}/`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: ['Users'],
    }),
    deleteUser: builder.mutation<void, number>({
      query: (id) => ({
        url: `/users/${id}/`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Users'],
    }),

    // Roles
    getRoles: builder.query<Role[], void>({
      query: () => '/users/roles/',
      providesTags: ['Roles'],
    }),

    // All Branches for dropdown
    getAllBranches: builder.query<Branch[], void>({
      query: () => '/branches/?page_size=1000',
      transformResponse: (response: { results: Branch[] }) => response.results,
      providesTags: ['Branches'],
    }),
  }),
})

// Types
export interface Supplier {
  id: number
  name: string
  code: string
  phone?: string
  email?: string
  address?: string
  tax_number?: string
  commercial_register?: string
  bank_name?: string
  bank_account?: string
  iban?: string
  notes?: string
  is_active: boolean
  total_payments?: number
  payments_count?: number
  created_at: string
}

export interface Branch {
  id: number
  name: string
  code: string
  address?: string
  phone?: string
  cost_center?: number
  cost_center_name?: string
  is_active: boolean
  banks_count?: number
  payments_count?: number
  created_at: string
}

export interface Bank {
  id: number
  name: string
  code: string
  account_number: string
  iban?: string
  swift_code?: string
  analytical_number?: string
  account_type: string
  currency: string
  balance: number
  branch?: number
  branch_name?: string
  is_active: boolean
  created_at: string
}

export interface CostCenter {
  id: number
  name: string
  code: string
  description?: string
  is_active: boolean
  branches_count?: number
  created_at: string
}

export interface PaymentRequest {
  id: number
  title?: string
  status: string
  total_requested: number
  total_approved: number
  branch?: number
  branch_name?: string
  supplier?: number
  supplier_name?: string
  bank?: number
  bank_name?: string
  cost_center?: number
  cost_center_name?: string
  notes?: string
  created_by?: number
  created_by_name?: string
  items?: PaymentItem[]
  created_at: string
}

export interface PaymentItem {
  id: number
  description: string
  requested_amount: number
  approved_amount?: number
}

export interface DashboardStats {
  branches_count: number
  suppliers_count: number
  banks_count: number
  total_payments: number
  pending_payments: number
  approved_payments: number
  rejected_payments: number
  today_payments: number
  this_month_total: number
  status_distribution: {
    status: string
    label: string
    count: number
    color: string
  }[]
  monthly_payments: {
    month: string
    month_name: string
    total: number
    count: number
  }[]
  top_suppliers: {
    name: string
    code: string
    total: number
    count: number
  }[]
  recent_payments: PaymentRequest[]
}

export interface Role {
  id: number
  name: string
  role_type: 'admin' | 'manager' | 'auditor' | 'branch_employee'
  role_type_display: string
  description?: string
  permissions_count?: number
  users_count?: number
  is_active: boolean
  is_system_role?: boolean
  created_at: string
}

export interface UserProfile {
  id: number
  role?: number
  role_name?: string
  role_type?: string
  branch?: number
  branch_name?: string
  phone?: string
  department?: string
  position?: string
}

export interface User {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  is_active: boolean
  is_staff: boolean
  is_superuser: boolean
  date_joined: string
  last_login?: string
  profile?: UserProfile
  role_name?: string
  role_type?: string
  branch_id?: number
  branch_name?: string
}

export const {
  useGetSuppliersQuery,
  useGetAllSuppliersQuery,
  useCreateSupplierMutation,
  useUpdateSupplierMutation,
  useDeleteSupplierMutation,
  useGetBranchesQuery,
  useCreateBranchMutation,
  useUpdateBranchMutation,
  useDeleteBranchMutation,
  useGetBanksQuery,
  useCreateBankMutation,
  useUpdateBankMutation,
  useDeleteBankMutation,
  useGetCostCentersQuery,
  useCreateCostCenterMutation,
  useUpdateCostCenterMutation,
  useDeleteCostCenterMutation,
  useGetPaymentsQuery,
  useGetPaymentQuery,
  useCreatePaymentMutation,
  useUpdatePaymentMutation,
  useDeletePaymentMutation,
  useGetDashboardQuery,
  useGetUsersQuery,
  useCreateUserMutation,
  useUpdateUserMutation,
  useDeleteUserMutation,
  useGetRolesQuery,
  useGetAllBranchesQuery,
} = api
