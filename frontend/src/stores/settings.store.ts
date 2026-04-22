import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ModelSettings } from '@/types'

interface SettingsStore {
  settings: ModelSettings
  updateSettings: (patch: Partial<ModelSettings>) => void
}

const defaultSettings: ModelSettings = {
  provider: 'openai',
  api_key: '',
  base_url: '',
  processing_model: 'gpt-4o-mini',
  chat_model: 'gpt-4o',
  embedding_model: 'text-embedding-3-small',
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      settings: defaultSettings,
      updateSettings: (patch) =>
        set((state) => ({ settings: { ...state.settings, ...patch } })),
    }),
    { name: 'readagent-settings' }
  )
)
