import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

// Define auth state type locally to avoid circular dependency
interface AuthState {
  tokens: {
    access: string
    refresh: string
  } | null
}

const baseQuery = fetchBaseQuery({
  baseUrl: '/api',
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
  tagTypes: ['Suppliers', 'Branches', 'Banks', 'CostCenters', 'Payments'],
  endpoints: (builder) => ({
    // Suppliers
    getSuppliers: builder.query<{ results: Supplier[]; count: number }, { page?: number; search?: string }>({
      query: ({ page = 1, search }) => ({
        url: '/suppliers/',
        params: { page, search },
      }),
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
    getBranches: builder.query<{ results: Branch[]; count: number }, { page?: number }>({
      query: ({ page = 1 }) => ({
        url: '/branches/',
        params: { page },
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
    getBanks: builder.query<{ results: Bank[]; count: number }, { page?: number }>({
      query: ({ page = 1 }) => ({
        url: '/banks/',
        params: { page },
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
    getCostCenters: builder.query<{ results: CostCenter[]; count: number }, { page?: number }>({
      query: ({ page = 1 }) => ({
        url: '/cost-centers/',
        params: { page },
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
    createPayment: builder.mutation<PaymentRequest, Partial<PaymentRequest>>({
      query: (data) => ({
        url: '/payments/',
        method: 'POST',
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

export const {
  useGetSuppliersQuery,
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
  useCreatePaymentMutation,
  useDeletePaymentMutation,
} = api
