import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

export function useUrlFilters() {
  const [params, setParams] = useSearchParams()
  const get = useCallback((key: string, fallback = '') => params.get(key) ?? fallback, [params])
  const set = useCallback((key: string, value: string | number | null | undefined) => {
    const next = new URLSearchParams(params)
    if (value === null || value === undefined || value === '') next.delete(key)
    else next.set(key, String(value))
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }, [params, setParams])
  const patch = useCallback((values: Record<string, string | number | null | undefined>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(values)) {
      if (value === null || value === undefined || value === '') next.delete(key)
      else next.set(key, String(value))
    }
    next.delete('page')
    setParams(next, { replace: true })
  }, [params, setParams])
  return { params, get, set, patch }
}
