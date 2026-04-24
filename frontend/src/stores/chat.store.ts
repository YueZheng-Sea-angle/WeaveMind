import { create } from 'zustand'

interface ChatStore {
  activeConversationId: number | null
  setActiveConversationId: (id: number | null) => void
}

export const useChatStore = create<ChatStore>((set) => ({
  activeConversationId: null,
  setActiveConversationId: (id) => set({ activeConversationId: id }),
}))
