import { apiClient } from './client'
import type { Conversation, Message } from '@/types'

export const conversationsApi = {
  list: (bookId: number) =>
    apiClient
      .get<Conversation[]>(`/books/${bookId}/conversations`)
      .then((r) => r.data),

  create: (bookId: number) =>
    apiClient
      .post<Conversation>(`/books/${bookId}/conversations`)
      .then((r) => r.data),

  messages: (bookId: number, conversationId: number) =>
    apiClient
      .get<Message[]>(`/books/${bookId}/conversations/${conversationId}/messages`)
      .then((r) => r.data),
}
