import { apiClient } from './client'
import type { RuntimeSettings, ModelSettingsUpdate } from '@/types'

export const settingsApi = {
  get: () =>
    apiClient.get<RuntimeSettings>('/settings').then((r) => r.data),

  /** 部分更新；空字符串会清除对应字段并回退到 .env */
  update: (patch: ModelSettingsUpdate) =>
    apiClient.put<RuntimeSettings>('/settings', patch).then((r) => r.data),

  /** 重置指定字段；不传 keys 则清空全部覆盖 */
  reset: (keys?: string[]) =>
    apiClient
      .post<RuntimeSettings>('/settings/reset', { keys: keys ?? null })
      .then((r) => r.data),
}
