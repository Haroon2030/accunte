import { InputHTMLAttributes, forwardRef } from 'react'
import { Search } from 'lucide-react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  searchMode?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, searchMode = false, className = '', ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-gray-700 mb-2">
            {label}
            {props.required && <span className="text-danger-500 mr-1">*</span>}
          </label>
        )}
        <div className="relative">
          {searchMode && (
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          )}
          <input
            ref={ref}
            className={`
              w-full px-4 py-2.5 bg-white border rounded-xl text-sm
              transition-all duration-200
              focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
              disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed
              placeholder:text-gray-400
              ${searchMode ? 'pr-10' : ''}
              ${error ? 'border-danger-500 focus:ring-danger-500' : 'border-gray-200'}
              ${className}
            `}
            {...props}
          />
        </div>
        {error && <p className="mt-1 text-sm text-danger-600">{error}</p>}
      </div>
    )
  }
)

Input.displayName = 'Input'
