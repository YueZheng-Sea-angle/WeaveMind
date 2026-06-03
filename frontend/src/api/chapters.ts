import { apiClient } from './client'
import type { Chapter, ChapterAnchor } from '@/types'

export interface ChapterCreateInput {
  title?: string | null
  raw_text: string
  chapter_number?: number | null
}

export interface ChapterUpdateInput {
  title?: string | null
  raw_text?: string | null
}

export const chaptersApi = {
  list: (bookId: number) =>
    apiClient.get<Chapter[]>(`/books/${bookId}/chapters`).then((r) => r.data),

  get: (bookId: number, chapterId: number) =>
    apiClient
      .get<Chapter>(`/books/${bookId}/chapters/${chapterId}`)
      .then((r) => r.data),

  create: (bookId: number, input: ChapterCreateInput) =>
    apiClient
      .post<Chapter>(`/books/${bookId}/chapters`, input)
      .then((r) => r.data),

  update: (bookId: number, chapterId: number, input: ChapterUpdateInput) =>
    apiClient
      .patch<Chapter>(`/books/${bookId}/chapters/${chapterId}`, input)
      .then((r) => r.data),

  remove: (bookId: number, chapterId: number) =>
    apiClient.delete(`/books/${bookId}/chapters/${chapterId}`),

  getAnchor: (bookId: number, chapterId: number) =>
    apiClient
      .get<ChapterAnchor>(`/books/${bookId}/chapters/${chapterId}/anchor`)
      .then((r) => r.data),

  updateAnchor: (bookId: number, chapterId: number, patch: Partial<ChapterAnchor>) =>
    apiClient
      .patch<ChapterAnchor>(`/books/${bookId}/chapters/${chapterId}/anchor`, patch)
      .then((r) => r.data),

  reprocess: (bookId: number, chapterId: number) =>
    apiClient
      .post<ChapterAnchor>(`/books/${bookId}/chapters/${chapterId}/reprocess`)
      .then((r) => r.data),
}
