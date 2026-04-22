import { create } from 'zustand'
import type { Book } from '@/types'

interface BookStore {
  books: Book[]
  currentBook: Book | null
  setBooks: (books: Book[]) => void
  setCurrentBook: (book: Book | null) => void
  updateBook: (id: number, patch: Partial<Book>) => void
}

export const useBookStore = create<BookStore>((set) => ({
  books: [],
  currentBook: null,

  setBooks: (books) => set({ books }),

  setCurrentBook: (book) => set({ currentBook: book }),

  updateBook: (id, patch) =>
    set((state) => ({
      books: state.books.map((b) => (b.id === id ? { ...b, ...patch } : b)),
      currentBook:
        state.currentBook?.id === id
          ? { ...state.currentBook, ...patch }
          : state.currentBook,
    })),
}))
