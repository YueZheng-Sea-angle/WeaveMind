import { apiClient } from './client'
import type { Entity, Relation } from '@/types'

export interface EntityListParams {
  entity_type?: string
  q?: string
}

export const entitiesApi = {
  list: (bookId: number, params?: EntityListParams) =>
    apiClient
      .get<Entity[]>(`/books/${bookId}/entities`, { params })
      .then((r) => r.data),

  get: (bookId: number, entityId: number) =>
    apiClient
      .get<Entity>(`/books/${bookId}/entities/${entityId}`)
      .then((r) => r.data),

  create: (bookId: number, data: Omit<Partial<Entity>, 'id' | 'book_id'>) =>
    apiClient
      .post<Entity>(`/books/${bookId}/entities`, data)
      .then((r) => r.data),

  update: (bookId: number, entityId: number, patch: Omit<Partial<Entity>, 'id' | 'book_id'>) =>
    apiClient
      .patch<Entity>(`/books/${bookId}/entities/${entityId}`, patch)
      .then((r) => r.data),

  delete: (bookId: number, entityId: number) =>
    apiClient.delete(`/books/${bookId}/entities/${entityId}`),

  relations: (bookId: number) =>
    apiClient
      .get<Relation[]>(`/books/${bookId}/relations`)
      .then((r) => r.data),
}
