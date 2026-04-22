import { useEffect } from 'react'
import { Outlet, useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { booksApi } from '@/api/books'
import { useBookStore } from '@/stores/book.store'

export function BookLayout() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const setCurrentBook = useBookStore((s) => s.setCurrentBook)

  const { data: book, isError } = useQuery({
    queryKey: ['book', id],
    queryFn: () => booksApi.get(Number(id)),
    enabled: !!id,
  })

  useEffect(() => {
    if (book) setCurrentBook(book)
    return () => setCurrentBook(null)
  }, [book, setCurrentBook])

  useEffect(() => {
    if (isError) navigate('/')
  }, [isError, navigate])

  return <Outlet />
}
