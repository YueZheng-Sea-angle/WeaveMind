import { create } from 'zustand'
import type { RuntimeSettings } from '@/types'

/**
 * 后端 RuntimeSettings 的客户端缓存（只读快照）。
 * - 仅保存非敏感字段，API Key 原文不会进入此 store 或 localStorage。
 * - SettingsPage 在加载 / 更新 / 重置时会调用 setSettings 同步。
 */
interface SettingsStore {
  settings: RuntimeSettings | null
  setSettings: (s: RuntimeSettings) => void
}

export const useSettingsStore = create<SettingsStore>((set) => ({
  settings: null,
  setSettings: (s) => set({ settings: s }),
}))
