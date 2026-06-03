import { apiClient } from './client'
import type { CharacterCard, CharacterCardEntry, CharacterCardCategory } from '@/types'

export interface CardCreateInput {
  name: string
  summary?: string | null
  entity_id?: number | null
  enabled?: boolean
}

export interface CardUpdateInput {
  name?: string
  summary?: string | null
  entity_id?: number | null
  enabled?: boolean
}

export interface EntryCreateInput {
  category: CharacterCardCategory
  title: string
  content?: string | null
  enabled?: boolean
  sort_order?: number
}

export interface EntryUpdateInput {
  category?: CharacterCardCategory
  title?: string
  content?: string | null
  enabled?: boolean
  sort_order?: number
}

export const characterCardsApi = {
  list: (bookId: number, q?: string) =>
    apiClient
      .get<CharacterCard[]>(`/books/${bookId}/character-cards`, {
        params: q ? { q } : undefined,
      })
      .then((r) => r.data),

  get: (bookId: number, cardId: number) =>
    apiClient
      .get<CharacterCard>(`/books/${bookId}/character-cards/${cardId}`)
      .then((r) => r.data),

  create: (bookId: number, data: CardCreateInput) =>
    apiClient
      .post<CharacterCard>(`/books/${bookId}/character-cards`, data)
      .then((r) => r.data),

  update: (bookId: number, cardId: number, patch: CardUpdateInput) =>
    apiClient
      .patch<CharacterCard>(`/books/${bookId}/character-cards/${cardId}`, patch)
      .then((r) => r.data),

  remove: (bookId: number, cardId: number) =>
    apiClient.delete(`/books/${bookId}/character-cards/${cardId}`),

  createEntry: (bookId: number, cardId: number, data: EntryCreateInput) =>
    apiClient
      .post<CharacterCardEntry>(
        `/books/${bookId}/character-cards/${cardId}/entries`,
        data,
      )
      .then((r) => r.data),

  updateEntry: (
    bookId: number,
    cardId: number,
    entryId: number,
    patch: EntryUpdateInput,
  ) =>
    apiClient
      .patch<CharacterCardEntry>(
        `/books/${bookId}/character-cards/${cardId}/entries/${entryId}`,
        patch,
      )
      .then((r) => r.data),

  removeEntry: (bookId: number, cardId: number, entryId: number) =>
    apiClient.delete(
      `/books/${bookId}/character-cards/${cardId}/entries/${entryId}`,
    ),
}
