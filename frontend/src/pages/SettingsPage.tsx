import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  RotateCcw,
  Save,
  Sparkles,
} from 'lucide-react'
import { settingsApi } from '@/api/settings'
import { useSettingsStore } from '@/stores/settings.store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import type { ModelSettingsUpdate, RuntimeSettings, SettingSource } from '@/types'

const MODEL_FIELDS = [
  {
    key: 'processing_model',
    label: '处理 Agent 模型',
    hint: '实体提取 / 锚点构建，建议低成本模型',
  },
  {
    key: 'chat_model',
    label: '对话大脑模型',
    hint: '主对话流，建议高质量模型',
  },
  {
    key: 'verifier_model',
    label: '验证 Agent 模型',
    hint: '可选交叉验证，建议高质量模型',
  },
] as const

type ModelKey = (typeof MODEL_FIELDS)[number]['key']

interface FormState {
  openai_api_key: string
  openai_base_url: string
  anthropic_api_key: string
  processing_model: string
  chat_model: string
  verifier_model: string
  embedding_model: string
  embedding_api_key: string
  embedding_base_url: string
}

function initialForm(remote: RuntimeSettings): FormState {
  return {
    openai_api_key: '',
    openai_base_url: remote.openai_base_url_source === 'user' ? remote.openai_base_url : '',
    anthropic_api_key: '',
    processing_model: remote.processing_model,
    chat_model: remote.chat_model,
    verifier_model: remote.verifier_model,
    embedding_model: remote.embedding_model,
    embedding_api_key: '',
    embedding_base_url: remote.embedding_base_url_source === 'user' ? remote.embedding_base_url : '',
  }
}

function SourceBadge({ source }: { source: SettingSource }) {
  if (source === 'user') {
    return (
      <Badge variant="default" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        用户设置
      </Badge>
    )
  }
  if (source === 'env') {
    return (
      <Badge variant="secondary" className="gap-1">
        <Sparkles className="h-3 w-3" />
        .env 默认
      </Badge>
    )
  }
  return (
    <Badge variant="destructive" className="gap-1">
      <AlertTriangle className="h-3 w-3" />
      未配置
    </Badge>
  )
}

export function SettingsPage() {
  const { data: remote, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
  })

  if (isLoading || !remote) {
    return (
      <div className="flex flex-1 flex-col overflow-auto p-6">
        <Skeleton className="mb-4 h-10 w-72" />
        <Skeleton className="mb-2 h-32 w-full max-w-2xl" />
        <Skeleton className="h-64 w-full max-w-2xl" />
      </div>
    )
  }

  // 使用 remote 内容作为 key，保证后端状态变化时表单重置为最新值
  return (
    <SettingsForm
      key={`${remote.openai_key_source}-${remote.anthropic_key_source}-${remote.embedding_key_source}-${remote.user_overrides.join(',')}`}
      remote={remote}
    />
  )
}

function SettingsForm({ remote }: { remote: RuntimeSettings }) {
  const queryClient = useQueryClient()
  const setStoreSettings = useSettingsStore((s) => s.setSettings)

  const [form, setForm] = useState<FormState>(() => initialForm(remote))
  const [showOpenAIKey, setShowOpenAIKey] = useState(false)
  const [showAnthropicKey, setShowAnthropicKey] = useState(false)
  const [showEmbeddingKey, setShowEmbeddingKey] = useState(false)
  const [savedTick, setSavedTick] = useState(false)

  const dirty = useMemo(() => {
    return (
      form.openai_api_key.length > 0 ||
      form.anthropic_api_key.length > 0 ||
      form.embedding_api_key.length > 0 ||
      form.openai_base_url !== (remote.openai_base_url_source === 'user' ? remote.openai_base_url : '') ||
      form.embedding_base_url !== (remote.embedding_base_url_source === 'user' ? remote.embedding_base_url : '') ||
      form.processing_model !== remote.processing_model ||
      form.chat_model !== remote.chat_model ||
      form.verifier_model !== remote.verifier_model ||
      form.embedding_model !== remote.embedding_model
    )
  }, [form, remote])

  const updateMutation = useMutation({
    mutationFn: (patch: ModelSettingsUpdate) => settingsApi.update(patch),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      setStoreSettings(data)
      setSavedTick(true)
      setTimeout(() => setSavedTick(false), 1800)
      setForm((f) => ({ ...f, openai_api_key: '', anthropic_api_key: '', embedding_api_key: '' }))
    },
  })

  const resetMutation = useMutation({
    mutationFn: (keys?: string[]) => settingsApi.reset(keys),
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      setStoreSettings(data)
    },
  })

  const handleSave = () => {
    const patch: ModelSettingsUpdate = {}

    if (form.openai_api_key) patch.openai_api_key = form.openai_api_key
    if (form.anthropic_api_key) patch.anthropic_api_key = form.anthropic_api_key
    if (form.embedding_api_key) patch.embedding_api_key = form.embedding_api_key

    if (
      form.openai_base_url !==
      (remote.openai_base_url_source === 'user' ? remote.openai_base_url : '')
    ) {
      patch.openai_base_url = form.openai_base_url
    }

    if (
      form.embedding_base_url !==
      (remote.embedding_base_url_source === 'user' ? remote.embedding_base_url : '')
    ) {
      patch.embedding_base_url = form.embedding_base_url
    }

    for (const { key } of MODEL_FIELDS) {
      const k = key as ModelKey
      if (form[k] !== remote[k]) {
        patch[k] = form[k]
      }
    }

    if (form.embedding_model !== remote.embedding_model) {
      patch.embedding_model = form.embedding_model
    }

    if (Object.keys(patch).length === 0) return
    updateMutation.mutate(patch)
  }

  const hasAnyKey = remote.has_openai_key || remote.has_anthropic_key

  return (
    <div className="flex flex-1 flex-col overflow-auto">
      <header className="border-b border-border px-6 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold">API 与模型设置</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              用户输入优先级最高；留空将自动回退到 .env 默认值
            </p>
          </div>
          <Badge variant={hasAnyKey ? 'default' : 'destructive'} className="gap-1">
            {hasAnyKey ? <CheckCircle2 className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
            {hasAnyKey ? 'API 已就绪' : '尚未配置 API'}
          </Badge>
        </div>
      </header>

      <div className="mx-auto w-full max-w-2xl flex-1 p-6">
        {!hasAnyKey && (
          <div className="mb-5 flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div className="flex-1">
              <p className="font-medium text-destructive">尚未检测到任何可用 API Key</p>
              <p className="mt-1 text-muted-foreground">
                请在下方输入 OpenAI 或 Anthropic 的 API Key，或者在后端{' '}
                <code className="rounded bg-muted px-1 py-0.5 text-xs">.env</code> 文件中配置。
                未配置前，实体提取、章节锚点、对话功能均无法正常运行。
              </p>
            </div>
          </div>
        )}

        {/* ── OpenAI 凭据 ────────────────────────────────────────────── */}
        <section className="mb-5 rounded-lg border border-border bg-card p-5">
          <div className="mb-4 flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">OpenAI 凭据</h2>
            <div className="ml-auto">
              <SourceBadge source={remote.openai_key_source} />
            </div>
          </div>

          <div className="flex flex-col gap-4">
            <div>
              <div className="mb-1 flex items-baseline justify-between">
                <label className="text-sm font-medium">API Key</label>
                {remote.openai_key_source === 'user' && (
                  <button
                    type="button"
                    onClick={() => resetMutation.mutate(['openai_api_key'])}
                    className="text-xs text-muted-foreground hover:text-destructive"
                  >
                    清除用户设置
                  </button>
                )}
              </div>
              <div className="relative">
                <Input
                  type={showOpenAIKey ? 'text' : 'password'}
                  value={form.openai_api_key}
                  onChange={(e) => setForm({ ...form, openai_api_key: e.target.value })}
                  placeholder={
                    remote.openai_key_source === 'user'
                      ? '已设置（输入新值以替换）'
                      : remote.openai_key_source === 'env'
                        ? '已从 .env 加载（输入此处可覆盖）'
                        : 'sk-...'
                  }
                  className="pr-9 font-mono"
                  autoComplete="off"
                />
                <button
                  type="button"
                  onClick={() => setShowOpenAIKey((s) => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  tabIndex={-1}
                >
                  {showOpenAIKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                此处输入的 Key 优先生效；不会写入 .env，仅持久化到服务端
                data/runtime_settings.json
              </p>
            </div>

            <div>
              <div className="mb-1 flex items-baseline justify-between">
                <label className="text-sm font-medium">Base URL（可选）</label>
                <SourceBadge source={remote.openai_base_url_source} />
              </div>
              <Input
                type="text"
                value={form.openai_base_url}
                onChange={(e) => setForm({ ...form, openai_base_url: e.target.value })}
                placeholder={remote.openai_base_url}
                className="font-mono"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                自定义网关 / 兼容端点；留空回退到 {remote.openai_base_url}
              </p>
            </div>
          </div>
        </section>

        {/* ── Anthropic 凭据 ────────────────────────────────────────── */}
        <section className="mb-5 rounded-lg border border-border bg-card p-5">
          <div className="mb-4 flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Anthropic 凭据（可选）</h2>
            <div className="ml-auto">
              <SourceBadge source={remote.anthropic_key_source} />
            </div>
          </div>

          <div>
            <div className="mb-1 flex items-baseline justify-between">
              <label className="text-sm font-medium">API Key</label>
              {remote.anthropic_key_source === 'user' && (
                <button
                  type="button"
                  onClick={() => resetMutation.mutate(['anthropic_api_key'])}
                  className="text-xs text-muted-foreground hover:text-destructive"
                >
                  清除用户设置
                </button>
              )}
            </div>
            <div className="relative">
              <Input
                type={showAnthropicKey ? 'text' : 'password'}
                value={form.anthropic_api_key}
                onChange={(e) => setForm({ ...form, anthropic_api_key: e.target.value })}
                placeholder={
                  remote.anthropic_key_source === 'user'
                    ? '已设置（输入新值以替换）'
                    : remote.anthropic_key_source === 'env'
                      ? '已从 .env 加载'
                      : 'sk-ant-...'
                }
                className="pr-9 font-mono"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowAnthropicKey((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                tabIndex={-1}
              >
                {showAnthropicKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
        </section>

        {/* ── Embedding 专属 API ───────────────────────────────────── */}
        <section className="mb-5 rounded-lg border border-border bg-card p-5">
          <div className="mb-1 flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">向量嵌入 API（可独立配置）</h2>
            <div className="ml-auto">
              <SourceBadge source={remote.embedding_key_source} />
            </div>
          </div>
          <p className="mb-4 text-xs text-muted-foreground">
            DeepSeek 等模型不提供 Embedding 接口，可在此填写 OpenAI 或其他兼容服务的凭据。
            留空则沿用上方主 API。
          </p>

          <div className="flex flex-col gap-4">
            <div>
              <div className="mb-1 flex items-baseline justify-between">
                <label className="text-sm font-medium">Embedding API Key</label>
                {remote.embedding_key_source === 'user' && (
                  <button
                    type="button"
                    onClick={() => resetMutation.mutate(['embedding_api_key'])}
                    className="text-xs text-muted-foreground hover:text-destructive"
                  >
                    清除用户设置
                  </button>
                )}
              </div>
              <div className="relative">
                <Input
                  type={showEmbeddingKey ? 'text' : 'password'}
                  value={form.embedding_api_key}
                  onChange={(e) => setForm({ ...form, embedding_api_key: e.target.value })}
                  placeholder={
                    remote.embedding_key_source === 'user'
                      ? '已设置（输入新值以替换）'
                      : remote.embedding_key_source === 'env'
                        ? '已从 .env 加载'
                        : '留空则沿用主 API Key'
                  }
                  className="pr-9 font-mono"
                  autoComplete="off"
                />
                <button
                  type="button"
                  onClick={() => setShowEmbeddingKey((s) => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  tabIndex={-1}
                >
                  {showEmbeddingKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div>
              <div className="mb-1 flex items-baseline justify-between">
                <label className="text-sm font-medium">Embedding Base URL（可选）</label>
                <SourceBadge source={remote.embedding_base_url_source} />
              </div>
              <Input
                type="text"
                value={form.embedding_base_url}
                onChange={(e) => setForm({ ...form, embedding_base_url: e.target.value })}
                placeholder="https://api.openai.com/v1（留空沿用主 API URL）"
                className="font-mono"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium">Embedding 模型名</label>
              <Input
                type="text"
                value={form.embedding_model}
                onChange={(e) => setForm({ ...form, embedding_model: e.target.value })}
                placeholder="text-embedding-3-small"
                className="font-mono"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                OpenAI 可用 text-embedding-3-small / text-embedding-ada-002
              </p>
            </div>
          </div>
        </section>

        {/* ── 模型分配 ──────────────────────────────────────────────── */}
        <section className="mb-5 rounded-lg border border-border bg-card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold">各 Agent 使用的模型</h2>
            <button
              type="button"
              onClick={() =>
                resetMutation.mutate([
                  'processing_model',
                  'chat_model',
                  'verifier_model',
                ])
              }
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              恢复默认
            </button>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {MODEL_FIELDS.map(({ key, label, hint }) => (
              <div key={key}>
                <label className="mb-1 block text-sm font-medium">{label}</label>
                <Input
                  type="text"
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  className="font-mono"
                />
                <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── 操作区 ────────────────────────────────────────────────── */}
        <div className="sticky bottom-0 -mx-6 -mb-6 mt-2 flex items-center justify-between gap-3 border-t border-border bg-background/95 px-6 py-3 backdrop-blur">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              if (window.confirm('确认重置所有用户设置，回退到 .env 默认值？')) {
                resetMutation.mutate(undefined)
              }
            }}
            disabled={remote.user_overrides.length === 0 || resetMutation.isPending}
          >
            <RotateCcw />
            重置全部
          </Button>

          <div className="flex items-center gap-2">
            {updateMutation.isError && (
              <span className="text-xs text-destructive">
                {(updateMutation.error as Error)?.message ?? '保存失败'}
              </span>
            )}
            <Button onClick={handleSave} disabled={!dirty || updateMutation.isPending}>
              {updateMutation.isPending ? <Loader2 className="animate-spin" /> : <Save />}
              {savedTick ? '已保存' : '保存设置'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// 兼容旧路由的命名导出
export { SettingsPage as BookSettingsPage }
