import { apiClient } from './client'
import type { Book } from '@/types'

export const booksApi = {
  list: () =>
    apiClient.get<Book[]>('/books').then((r) => r.data),

  get: (id: number) =>
    apiClient.get<Book>(`/books/${id}`).then((r) => r.data),

  upload: (file: File, title: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('title', title)
    return apiClient
      .post<Book>('/books/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  delete: (id: number) => apiClient.delete(`/books/${id}`),
}
