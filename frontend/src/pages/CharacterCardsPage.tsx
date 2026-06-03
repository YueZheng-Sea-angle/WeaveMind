import { useState, useDeferredValue } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  IdCard,
  X,
  ChevronRight,
  Edit2,
  Check,
  Plus,
  Trash2,
  Loader2,
} from 'lucide-react'
import { characterCardsApi } from '@/api/characterCards'
import type {
  CharacterCard,
  CharacterCardEntry,
  CharacterCardCategory,
} from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

const CATEGORY_CONFIG: Array<{ key: CharacterCardCategory; label: string }> = [
  { key: 'biography', label: '生平' },
  { key: 'personality', label: '性格特点' },
  { key: 'relationship', label: '人物关系' },
  { key: 'skill', label: '技能' },
  { key: 'item', label: '道具' },
  { key: 'status', label: '当前状态' },
  { key: 'foreshadowing', label: '关键伏笔' },
]

/* ───────────────────────────── Toggle 开关 ───────────────────────────── */

function Toggle({
  enabled,
  onChange,
  disabled,
  title,
}: {
  enabled: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  title?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      title={title ?? (enabled ? '已启用（点击停用）' : '已停用（点击启用）')}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation()
        onChange(!enabled)
      }}
      className={cn(
        'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors',
        enabled ? 'bg-primary' : 'bg-muted-foreground/30',
        disabled && 'opacity-50',
      )}
    >
      <span
        className={cn(
          'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
          enabled ? 'translate-x-4' : 'translate-x-0.5',
        )}
      />
    </button>
  )
}

/* ───────────────────────────── 页面主体 ───────────────────────────── */

export function CharacterCardsPage() {
  const { id } = useParams<{ id: string }>()
  const bookId = Number(id)
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)

  const deferredSearch = useDeferredValue(search)

  const { data: cards, isLoading } = useQuery({
    queryKey: ['character-cards', bookId, deferredSearch],
    queryFn: () => characterCardsApi.list(bookId, deferredSearch || undefined),
    enabled: Boolean(bookId),
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['character-cards', bookId] })

  const selectedCard = cards?.find((c) => c.id === selectedId) ?? null

  const toggleCardMutation = useMutation({
    mutationFn: ({ cardId, enabled }: { cardId: number; enabled: boolean }) =>
      characterCardsApi.update(bookId, cardId, { enabled }),
    onSuccess: invalidate,
  })

  return (
    <div className="flex h-full overflow-hidden">
      {/* 左侧：角色卡列表 */}
      <div
        className={cn(
          'flex flex-col border-r bg-background transition-[width] duration-200',
          selectedCard ? 'w-[360px] min-w-[300px]' : 'flex-1',
        )}
      >
        <div className="p-4 space-y-3 border-b shrink-0">
          <div className="flex items-center justify-between gap-2">
            <h1 className="text-sm font-semibold">关键角色卡</h1>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => {
                setAdding(true)
                setSelectedId(null)
              }}
            >
              <Plus className="h-3.5 w-3.5" />
              新建角色
            </Button>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              placeholder="搜索角色名..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : !cards?.length ? (
            <div className="flex flex-col items-center justify-center h-40 gap-2 text-muted-foreground">
              <IdCard className="h-8 w-8 opacity-30" />
              <p className="text-sm">
                {search ? '未找到匹配角色卡' : '暂无角色卡'}
              </p>
              <p className="text-xs opacity-70">
                章节分析会自动生成，也可手动新建
              </p>
            </div>
          ) : (
            <div className="divide-y">
              {cards.map((card) => (
                <CardRow
                  key={card.id}
                  card={card}
                  isSelected={selectedId === card.id}
                  onClick={() => {
                    setAdding(false)
                    setSelectedId((prev) => (prev === card.id ? null : card.id))
                  }}
                  onToggle={(enabled) =>
                    toggleCardMutation.mutate({ cardId: card.id, enabled })
                  }
                />
              ))}
            </div>
          )}
        </div>

        {cards && (
          <div className="px-4 py-2 border-t text-xs text-muted-foreground shrink-0">
            共 {cards.length} 张角色卡
          </div>
        )}
      </div>

      {/* 右侧：详情 / 新建 */}
      {adding ? (
        <AddCardPanel
          bookId={bookId}
          onCancel={() => setAdding(false)}
          onCreated={(created) => {
            setAdding(false)
            invalidate()
            setSelectedId(created.id)
          }}
        />
      ) : selectedCard ? (
        <CardDetailPanel
          key={selectedCard.id}
          card={selectedCard}
          bookId={bookId}
          onClose={() => setSelectedId(null)}
          onChanged={invalidate}
        />
      ) : null}
    </div>
  )
}

/* ───────────────────────────── CardRow ───────────────────────────── */

function CardRow({
  card,
  isSelected,
  onClick,
  onToggle,
}: {
  card: CharacterCard
  isSelected: boolean
  onClick: () => void
  onToggle: (enabled: boolean) => void
}) {
  const enabledEntries = card.entries.filter((e) => e.enabled).length
  return (
    <button
      className={cn(
        'w-full px-4 py-3 text-left flex items-start gap-3 hover:bg-accent/60 transition-colors',
        isSelected && 'bg-accent',
        !card.enabled && 'opacity-50',
      )}
      onClick={onClick}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="font-medium text-sm truncate">{card.name}</span>
          {!card.enabled && (
            <span className="text-[10px] rounded-full bg-muted px-1.5 py-0.5 text-muted-foreground shrink-0">
              已停用
            </span>
          )}
        </div>
        {card.summary ? (
          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
            {card.summary}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground/60 italic">无简介</p>
        )}
        <p className="text-[11px] text-muted-foreground/70 mt-0.5">
          {enabledEntries} / {card.entries.length} 条目启用
        </p>
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <Toggle enabled={card.enabled} onChange={onToggle} />
        <ChevronRight
          className={cn(
            'h-4 w-4 text-muted-foreground transition-transform duration-150',
            isSelected && 'rotate-90',
          )}
        />
      </div>
    </button>
  )
}

/* ───────────────────────────── AddCardPanel ───────────────────────────── */

function AddCardPanel({
  bookId,
  onCancel,
  onCreated,
}: {
  bookId: number
  onCancel: () => void
  onCreated: (created: CharacterCard) => void
}) {
  const [name, setName] = useState('')
  const [summary, setSummary] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      characterCardsApi.create(bookId, {
        name: name.trim(),
        summary: summary.trim() || null,
      }),
    onSuccess: (created) => onCreated(created),
  })

  const canSubmit = name.trim().length > 0 && !mutation.isPending

  return (
    <div className="flex flex-col flex-1 overflow-hidden border-l">
      <div className="flex items-center justify-between px-5 py-4 border-b shrink-0">
        <h2 className="text-base font-semibold">新建角色卡</h2>
        <Button variant="ghost" size="icon" onClick={onCancel} title="取消">
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        <div className="space-y-2">
          <Label>角色名称</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="如：林惊鸿"
            autoFocus
          />
        </div>
        <div className="space-y-2">
          <Label>简介（可选）</Label>
          <Textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows={4}
            className="resize-none"
            placeholder="一句话概括该角色..."
          />
        </div>
        {mutation.isError && (
          <p className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
            创建失败：{(mutation.error as Error)?.message}
          </p>
        )}
      </div>
      <div className="flex justify-end gap-2 border-t px-5 py-3 shrink-0">
        <Button variant="outline" size="sm" onClick={onCancel} disabled={mutation.isPending}>
          取消
        </Button>
        <Button size="sm" onClick={() => mutation.mutate()} disabled={!canSubmit} className="gap-1.5">
          {mutation.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5" />
          )}
          创建
        </Button>
      </div>
    </div>
  )
}

/* ───────────────────────────── CardDetailPanel ───────────────────────────── */

function CardDetailPanel({
  card,
  bookId,
  onClose,
  onChanged,
}: {
  card: CharacterCard
  bookId: number
  onClose: () => void
  onChanged: () => void
}) {
  const [editingHeader, setEditingHeader] = useState(false)
  const [name, setName] = useState(card.name)
  const [summary, setSummary] = useState(card.summary ?? '')

  const updateCard = useMutation({
    mutationFn: (patch: Parameters<typeof characterCardsApi.update>[2]) =>
      characterCardsApi.update(bookId, card.id, patch),
    onSuccess: () => {
      setEditingHeader(false)
      onChanged()
    },
  })

  const deleteCard = useMutation({
    mutationFn: () => characterCardsApi.remove(bookId, card.id),
    onSuccess: () => {
      onClose()
      onChanged()
    },
  })

  const handleSaveHeader = () => {
    updateCard.mutate({ name: name.trim() || card.name, summary: summary.trim() || null })
  }

  const handleDelete = () => {
    if (!window.confirm(`确定删除角色卡「${card.name}」及其全部条目吗？此操作不可恢复。`)) return
    deleteCard.mutate()
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden border-l">
      {/* 头部 */}
      <div className="flex items-center gap-2 px-5 py-4 border-b shrink-0">
        <div className="flex-1 min-w-0">
          {editingHeader ? (
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-8 font-semibold"
            />
          ) : (
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold truncate">{card.name}</h2>
              {!card.enabled && (
                <span className="text-[10px] rounded-full bg-muted px-1.5 py-0.5 text-muted-foreground shrink-0">
                  已停用
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-xs text-muted-foreground">整卡</span>
          <Toggle
            enabled={card.enabled}
            onChange={(enabled) => updateCard.mutate({ enabled })}
            disabled={updateCard.isPending}
          />
        </div>

        {!editingHeader ? (
          <Button variant="ghost" size="icon" onClick={() => setEditingHeader(true)} title="编辑名称/简介">
            <Edit2 className="h-4 w-4" />
          </Button>
        ) : (
          <div className="flex gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                setName(card.name)
                setSummary(card.summary ?? '')
                setEditingHeader(false)
              }}
              title="取消"
            >
              <X className="h-4 w-4" />
            </Button>
            <Button size="icon" onClick={handleSaveHeader} disabled={updateCard.isPending} title="保存">
              <Check className="h-4 w-4" />
            </Button>
          </div>
        )}

        <Button
          variant="ghost"
          size="icon"
          className="text-muted-foreground hover:text-destructive"
          onClick={handleDelete}
          disabled={deleteCard.isPending}
          title="删除角色卡"
        >
          <Trash2 className="h-4 w-4" />
        </Button>

        <Button variant="ghost" size="icon" onClick={onClose} title="关闭">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* 正文 */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {updateCard.isError && (
          <p className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
            保存失败：{(updateCard.error as Error)?.message}
          </p>
        )}

        {/* 简介 */}
        <div className="space-y-2">
          <Label>简介</Label>
          {editingHeader ? (
            <Textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              rows={3}
              className="resize-none"
              placeholder="一句话概括该角色..."
            />
          ) : card.summary ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{card.summary}</p>
          ) : (
            <p className="text-sm text-muted-foreground italic">暂无简介</p>
          )}
        </div>

        <Separator />

        {/* 分类条目 */}
        {CATEGORY_CONFIG.map(({ key, label }) => (
          <CategorySection
            key={key}
            bookId={bookId}
            cardId={card.id}
            category={key}
            label={label}
            entries={card.entries.filter((e) => e.category === key)}
            onChanged={onChanged}
          />
        ))}
      </div>
    </div>
  )
}

/* ───────────────────────────── CategorySection ───────────────────────────── */

function CategorySection({
  bookId,
  cardId,
  category,
  label,
  entries,
  onChanged,
}: {
  bookId: number
  cardId: number
  category: CharacterCardCategory
  label: string
  entries: CharacterCardEntry[]
  onChanged: () => void
}) {
  const [adding, setAdding] = useState(false)
  const enabledCount = entries.filter((e) => e.enabled).length

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          {entries.length > 0 && (
            <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {enabledCount}/{entries.length}
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 gap-1 text-[11px] px-1.5"
          onClick={() => setAdding((v) => !v)}
        >
          <Plus className="h-3 w-3" />
          添加
        </Button>
      </div>

      {entries.length === 0 && !adding ? (
        <p className="text-xs text-muted-foreground/60 italic">暂无条目</p>
      ) : (
        <div className="space-y-1.5">
          {entries.map((entry) => (
            <EntryRow
              key={entry.id}
              bookId={bookId}
              cardId={cardId}
              entry={entry}
              onChanged={onChanged}
            />
          ))}
        </div>
      )}

      {adding && (
        <AddEntryForm
          bookId={bookId}
          cardId={cardId}
          category={category}
          onCancel={() => setAdding(false)}
          onCreated={() => {
            setAdding(false)
            onChanged()
          }}
        />
      )}
    </div>
  )
}

/* ───────────────────────────── EntryRow ───────────────────────────── */

function EntryRow({
  bookId,
  cardId,
  entry,
  onChanged,
}: {
  bookId: number
  cardId: number
  entry: CharacterCardEntry
  onChanged: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(entry.title)
  const [content, setContent] = useState(entry.content ?? '')

  const updateEntry = useMutation({
    mutationFn: (patch: Parameters<typeof characterCardsApi.updateEntry>[3]) =>
      characterCardsApi.updateEntry(bookId, cardId, entry.id, patch),
    onSuccess: () => {
      setEditing(false)
      onChanged()
    },
  })

  const deleteEntry = useMutation({
    mutationFn: () => characterCardsApi.removeEntry(bookId, cardId, entry.id),
    onSuccess: onChanged,
  })

  const handleDelete = () => {
    if (!window.confirm(`确定删除条目「${entry.title}」吗？`)) return
    deleteEntry.mutate()
  }

  if (editing) {
    return (
      <div className="rounded-md border border-border bg-card p-2.5 space-y-2">
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="条目标题"
          className="h-8"
        />
        <Textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={3}
          className="resize-none text-sm"
          placeholder="条目内容"
        />
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={() => {
              setTitle(entry.title)
              setContent(entry.content ?? '')
              setEditing(false)
            }}
          >
            <X className="h-3.5 w-3.5" />
            取消
          </Button>
          <Button
            size="sm"
            className="h-7 gap-1 text-xs"
            disabled={updateEntry.isPending || !title.trim()}
            onClick={() =>
              updateEntry.mutate({ title: title.trim(), content: content.trim() || null })
            }
          >
            {updateEntry.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Check className="h-3.5 w-3.5" />
            )}
            保存
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'group flex items-start gap-2 rounded-md border border-border bg-card px-2.5 py-2',
        !entry.enabled && 'opacity-50',
      )}
    >
      <Toggle
        enabled={entry.enabled}
        onChange={(enabled) => updateEntry.mutate({ enabled })}
        disabled={updateEntry.isPending}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium truncate">{entry.title}</span>
          {!entry.enabled && (
            <span className="text-[10px] rounded-full bg-muted px-1.5 py-0.5 text-muted-foreground shrink-0">
              已停用
            </span>
          )}
        </div>
        {entry.content && (
          <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap mt-0.5">
            {entry.content}
          </p>
        )}
      </div>
      <div className="flex gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setEditing(true)}
          title="编辑"
        >
          <Edit2 className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={handleDelete}
          disabled={deleteEntry.isPending}
          title="删除"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}

/* ───────────────────────────── AddEntryForm ───────────────────────────── */

function AddEntryForm({
  bookId,
  cardId,
  category,
  onCancel,
  onCreated,
}: {
  bookId: number
  cardId: number
  category: CharacterCardCategory
  onCancel: () => void
  onCreated: () => void
}) {
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      characterCardsApi.createEntry(bookId, cardId, {
        category,
        title: title.trim(),
        content: content.trim() || null,
      }),
    onSuccess: onCreated,
  })

  return (
    <div className="rounded-md border border-dashed border-border bg-accent/20 p-2.5 space-y-2">
      <Input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="条目标题"
        className="h-8"
        autoFocus
      />
      <Textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={2}
        className="resize-none text-sm"
        placeholder="条目内容（可选）"
      />
      {mutation.isError && (
        <p className="text-xs text-destructive">
          {(mutation.error as Error)?.message}
        </p>
      )}
      <div className="flex justify-end gap-1">
        <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={onCancel}>
          <X className="h-3.5 w-3.5" />
          取消
        </Button>
        <Button
          size="sm"
          className="h-7 gap-1 text-xs"
          disabled={mutation.isPending || !title.trim()}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5" />
          )}
          添加
        </Button>
      </div>
    </div>
  )
}

/* ───────────────────────────── 小工具组件 ───────────────────────────── */

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
      {children}
    </p>
  )
}
