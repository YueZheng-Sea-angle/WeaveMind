import { apiClient } from './client'
import type { Chapter, ChapterAnchor } from '@/types'

export const chaptersApi = {
  list: (bookId: number) =>
    apiClient.get<Chapter[]>(`/books/${bookId}/chapters`).then((r) => r.data),

  get: (bookId: number, chapterId: number) =>
    apiClient
      .get<Chapter>(`/books/${bookId}/chapters/${chapterId}`)
      .then((r) => r.data),

  getAnchor: (bookId: number, chapterId: number) =>
    apiClient
      .get<ChapterAnchor>(`/books/${bookId}/chapters/${chapterId}/anchor`)
      .then((r) => r.data),

  updateAnchor: (bookId: number, chapterId: number, patch: Partial<ChapterAnchor>) =>
    apiClient
      .patch<ChapterAnchor>(`/books/${bookId}/chapters/${chapterId}/anchor`, patch)
      .then((r) => r.data),
}
