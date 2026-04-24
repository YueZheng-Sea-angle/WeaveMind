import { apiClient } from './client'
import type { Book } from '@/types'

export const booksApi = {
  list: () =>
    apiClient.get<Book[]>('/books').then((r) => r.data),

  get: (id: number) =>
    apiClient.get<Book>(`/books/${id}`).then((r) => r.data),

  create: (title: string) =>
    apiClient
      .post<Book>('/books', { title })
      .then((r) => r.data),

  upload: (bookId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient
      .post<Book>(`/books/${bookId}/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  triggerProcess: (id: number) =>
    apiClient.post(`/books/${id}/process`).then((r) => r.data),

  delete: (id: number) => apiClient.delete(`/books/${id}`),
}
