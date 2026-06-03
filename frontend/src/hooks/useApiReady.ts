import { useQuery } from '@tanstack/react-query'
import { settingsApi } from '@/api/settings'
import { useSettingsStore } from '@/stores/settings.store'
import type { RuntimeSettings } from '@/types'

/**
 * 读取后端运行时设置，并把快照同步到 store。
 * 用于全局判断"是否已配置 API Key"。
 */
export function useApiReady(): { ready: boolean; loading: boolean; data: RuntimeSettings | null } {
  const setStoreSettings = useSettingsStore((s) => s.setSettings)

  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const s = await settingsApi.get()
      setStoreSettings(s)
      return s
    },
    staleTime: 1000 * 60,
  })

  return {
    ready: !!(data && (data.has_openai_key || data.has_anthropic_key)),
    loading: isLoading,
    data: data ?? null,
  }
}
