import { apiClient } from './client'
import type { ModelSettings } from '@/types'

export const settingsApi = {
  get: () =>
    apiClient.get<ModelSettings>('/settings').then((r) => r.data),

  update: (settings: Partial<ModelSettings>) =>
    apiClient.post<ModelSettings>('/settings', settings).then((r) => r.data),
}
