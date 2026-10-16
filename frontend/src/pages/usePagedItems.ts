import { useEffect, useState, type RefObject } from 'react'

type Flag = { current: boolean }

export function usePagedItems<T>(
  page: { items: T[] } | undefined,
  cursor?: string,
  loadingMore?: Flag,
  statusRef?: RefObject<HTMLElement | null>,
) {
  const [items, setItems] = useState<T[]>([])
  useEffect(() => {
    if (!page) return
    setItems((current) => cursor ? [...current, ...page.items] : page.items)
    if (loadingMore?.current) {
      loadingMore.current = false
      requestAnimationFrame(() => statusRef?.current?.focus())
    }
  }, [cursor, loadingMore, page, statusRef])
  return [items, setItems] as const
}
