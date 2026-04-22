import { apiClient } from './client'
import type { Entity, Relation } from '@/types'

export const entitiesApi = {
  list: (bookId: number, type?: string) =>
    apiClient
      .get<Entity[]>(`/books/${bookId}/entities`, { params: { type } })
      .then((r) => r.data),

  get: (bookId: number, entityId: number) =>
    apiClient
      .get<Entity>(`/books/${bookId}/entities/${entityId}`)
      .then((r) => r.data),

  update: (bookId: number, entityId: number, patch: Partial<Entity>) =>
    apiClient
      .patch<Entity>(`/books/${bookId}/entities/${entityId}`, patch)
      .then((r) => r.data),

  relations: (bookId: number) =>
    apiClient
      .get<Relation[]>(`/books/${bookId}/relations`)
      .then((r) => r.data),
}
