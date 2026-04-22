import { useState } from 'react'
import { useSettingsStore } from '@/stores/settings.store'
import { Button } from '@/components/ui/button'
import { Save } from 'lucide-react'

const providers = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'custom', label: '自定义' },
] as const

export function BookSettingsPage() {
  const { settings, updateSettings } = useSettingsStore()
  const [local, setLocal] = useState(settings)
  const [saved, setSaved] = useState(false)

  const handleSave = () => {
    updateSettings(local)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="flex flex-1 flex-col overflow-auto">
      <header className="border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold">模型设置</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">配置 AI 提供商与模型选择</p>
      </header>

      <div className="mx-auto w-full max-w-lg flex-1 overflow-auto p-6">
        <div className="flex flex-col gap-5">
          <div>
            <label className="mb-1 block text-sm font-medium">AI 提供商</label>
            <select
              value={local.provider}
              onChange={(e) =>
                setLocal({ ...local, provider: e.target.value as typeof local.provider })
              }
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              {providers.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">API Key</label>
            <input
              type="password"
              value={local.api_key}
              onChange={(e) => setLocal({ ...local, api_key: e.target.value })}
              placeholder="sk-..."
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          {local.provider === 'custom' && (
            <div>
              <label className="mb-1 block text-sm font-medium">Base URL</label>
              <input
                type="text"
                value={local.base_url ?? ''}
                onChange={(e) => setLocal({ ...local, base_url: e.target.value })}
                placeholder="https://..."
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          )}

          <div className="rounded-lg border border-border p-4">
            <p className="mb-3 text-sm font-medium">模型分配</p>
            <div className="flex flex-col gap-3">
              {[
                { key: 'processing_model', label: '处理 Agent（实体提取/锚点构建）' },
                { key: 'chat_model', label: '对话 Brain' },
                { key: 'embedding_model', label: '文本嵌入' },
              ].map(({ key, label }) => (
                <div key={key}>
                  <label className="mb-1 block text-xs text-muted-foreground">{label}</label>
                  <input
                    type="text"
                    value={local[key as keyof typeof local] as string}
                    onChange={(e) => setLocal({ ...local, [key]: e.target.value })}
                    className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm font-mono focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>
              ))}
            </div>
          </div>

          <Button onClick={handleSave} className="self-start">
            <Save />
            {saved ? '已保存' : '保存设置'}
          </Button>
        </div>
      </div>
    </div>
  )
}
