import { useMemo, useState } from 'react'

// Click-to-sort for the small in-memory tables. Returns the sorted rows plus a
// `sort(key)` toggler and the current `{ key, dir }` for header indicators.
// Nullish values always sort last; numbers compare numerically, everything else
// as case-insensitive strings.
export function useSortable(rows, initialKey = null, initialDir = 'asc') {
  const [key, setKey] = useState(initialKey)
  const [dir, setDir] = useState(initialDir)

  const sort = (k) => {
    if (k === key) {
      setDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setKey(k)
      setDir('asc')
    }
  }

  const sorted = useMemo(() => {
    if (!key) return rows
    const mul = dir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = a[key]
      const bv = b[key]
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * mul
      return String(av).toLowerCase().localeCompare(String(bv).toLowerCase()) * mul
    })
  }, [rows, key, dir])

  return { sorted, sort, key, dir }
}
