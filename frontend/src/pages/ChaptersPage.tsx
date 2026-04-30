import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  List,
  BookText,
  Anchor,
  Edit2,
  Check,
  X,
  ChevronRight,
  Sparkles,
  Users,
  Eye,
  AlertCircle,
} from 'lucide-react'
import { chaptersApi } from '@/api/chapters'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import type { Chapter, ChapterAnchor } from '@/types'

type RightTab = 'text' | 'anchor'

export function ChaptersPage() {
  const { id } = useParams<{ id: string }>()
  const bookId = Number(id)
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<RightTab>('anchor')

  const { data: chapters = [], isLoading } = useQuery({
    queryKey: ['chapters', bookId],
    queryFn: () => chaptersApi.list(bookId),
    enabled: Number.isFinite(bookId),
  })

  useEffect(() => {
    if (!selectedChapterId && chapters.length > 0) {
      setSelectedChapterId(chapters[0].id)
    }
  }, [chapters, selectedChapterId])

  const { data: chapterDetail, isLoading: isChapterLoading } = useQuery({
    queryKey: ['chapter', bookId, selectedChapterId],
    queryFn: () => chaptersApi.get(bookId, selectedChapterId as number),
    enabled: Number.isFinite(bookId) && selectedChapterId != null,
  })

  const { data: anchor, isLoading: isAnchorLoading } = useQuery({
    queryKey: ['anchor', bookId, selectedChapterId],
    queryFn: () => chaptersApi.getAnchor(bookId, selectedChapterId as number),
    enabled: Number.isFinite(bookId) && selectedChapterId != null,
    retry: false,
  })

  const renderChapterItem = (chapter: Chapter) => {
    const isActive = chapter.id === selectedChapterId
    return (
      <button
        key={chapter.id}
        type="button"
        onClick={() => setSelectedChapterId(chapter.id)}
        className={cn(
          'w-full rounded-md border px-3 py-2 text-left transition-colors',
          isActive
            ? 'border-primary bg-primary/5'
            : 'border-border bg-card hover:bg-accent/30',
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-medium">
            第 {chapter.chapter_number} 章{chapter.title ? ` · ${chapter.title}` : ''}
          </p>
          <ChevronRight
            className={cn(
              'h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-150',
              isActive && 'rotate-90',
            )}
          />
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{chapter.word_count} 字</p>
      </button>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="shrink-0 border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold">章节锚点</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          浏览章节正文与 AI 生成的结构化锚点，支持直接编辑
        </p>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-4 overflow-hidden p-4 md:grid-cols-[280px_1fr]">
        {/* 左侧：章节列表 */}
        <section className="flex flex-col overflow-hidden rounded-lg border border-border">
          <div className="shrink-0 border-b border-border px-3 py-2 text-sm font-medium">
            分章列表{chapters.length > 0 ? ` (${chapters.length})` : ''}
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto p-3">
            {isLoading ? (
              <>
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </>
            ) : chapters.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
                <List className="h-8 w-8 opacity-30" />
                <p className="text-sm">还没有章节数据</p>
              </div>
            ) : (
              chapters.map(renderChapterItem)
            )}
          </div>
        </section>

        {/* 右侧：内容区 */}
        <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border">
          {chapterDetail ? (
            <>
              {/* 章节标题 + Tab 切换 */}
              <div className="shrink-0 border-b border-border px-4">
                <div className="flex items-center justify-between py-3">
                  <h2 className="text-sm font-semibold">
                    第 {chapterDetail.chapter_number} 章
                    {chapterDetail.title ? ` · ${chapterDetail.title}` : ''}
                  </h2>
                  <span className="text-xs text-muted-foreground">
                    {chapterDetail.word_count} 字
                  </span>
                </div>
                <div className="flex gap-1 pb-0">
                  <TabButton
                    active={activeTab === 'anchor'}
                    onClick={() => setActiveTab('anchor')}
                    icon={<Anchor className="h-3.5 w-3.5" />}
                    label="章节锚点"
                  />
                  <TabButton
                    active={activeTab === 'text'}
                    onClick={() => setActiveTab('text')}
                    icon={<BookText className="h-3.5 w-3.5" />}
                    label="原文"
                  />
                </div>
              </div>

              {/* Tab 内容 */}
              <div className="flex-1 overflow-y-auto">
                {activeTab === 'text' ? (
                  <div className="p-5">
                    <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-7 text-foreground">
                      {chapterDetail.raw_text}
                    </pre>
                  </div>
                ) : (
                  <AnchorPanel
                    bookId={bookId}
                    chapterId={chapterDetail.id}
                    anchor={anchor}
                    isLoading={isAnchorLoading}
                  />
                )}
              </div>
            </>
          ) : isChapterLoading ? (
            <div className="p-5 space-y-3">
              <Skeleton className="h-6 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
              <BookText className="h-8 w-8 opacity-30" />
              <p className="text-sm">请选择一个章节查看内容</p>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

/* ─────────────────────────── TabButton ─────────────────────────── */

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-t-md px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px',
        active
          ? 'border-primary text-primary'
          : 'border-transparent text-muted-foreground hover:text-foreground',
      )}
    >
      {icon}
      {label}
    </button>
  )
}

/* ─────────────────────────── AnchorPanel ─────────────────────────── */

interface AnchorPanelProps {
  bookId: number
  chapterId: number
  anchor: ChapterAnchor | undefined
  isLoading: boolean
}

interface AnchorEditForm {
  summary: string
  key_events: string
  characters_present: string
  foreshadowing: string
  themes: string
}

function AnchorPanel({ bookId, chapterId, anchor, isLoading }: AnchorPanelProps) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<AnchorEditForm>({
    summary: '',
    key_events: '',
    characters_present: '',
    foreshadowing: '',
    themes: '',
  })

  useEffect(() => {
    if (anchor) {
      setForm({
        summary: anchor.summary ?? '',
        key_events: anchor.key_events.join('\n'),
        characters_present: anchor.characters_present.join('\n'),
        foreshadowing: anchor.foreshadowing.join('\n'),
        themes: anchor.themes.join('\n'),
      })
      setEditing(false)
    }
  }, [anchor])

  const mutation = useMutation({
    mutationFn: (patch: Partial<ChapterAnchor>) =>
      chaptersApi.updateAnchor(bookId, chapterId, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['anchor', bookId, chapterId] })
      setEditing(false)
    },
  })

  const handleEdit = () => {
    if (!anchor) return
    setForm({
      summary: anchor.summary ?? '',
      key_events: anchor.key_events.join('\n'),
      characters_present: anchor.characters_present.join('\n'),
      foreshadowing: anchor.foreshadowing.join('\n'),
      themes: anchor.themes.join('\n'),
    })
    setEditing(true)
  }

  const handleCancel = () => {
    setEditing(false)
  }

  const handleSave = () => {
    const splitLines = (s: string) =>
      s
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)

    mutation.mutate({
      summary: form.summary.trim() || anchor?.summary,
      key_events: splitLines(form.key_events),
      characters_present: splitLines(form.characters_present),
      foreshadowing: splitLines(form.foreshadowing),
      themes: splitLines(form.themes),
    })
  }

  if (isLoading) {
    return (
      <div className="p-5 space-y-4">
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-4 w-1/4" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  if (!anchor) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
        <AlertCircle className="h-8 w-8 opacity-30" />
        <p className="text-sm">该章节锚点尚未生成</p>
        <p className="text-xs opacity-70">处理完成后锚点将自动填充</p>
      </div>
    )
  }

  return (
    <div className="p-5 space-y-5">
      {/* 操作栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" />
          <span>AI 生成锚点</span>
        </div>
        {!editing ? (
          <Button variant="ghost" size="sm" onClick={handleEdit} className="gap-1.5 text-xs h-7">
            <Edit2 className="h-3.5 w-3.5" />
            编辑
          </Button>
        ) : (
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={handleCancel} className="gap-1 text-xs h-7">
              <X className="h-3.5 w-3.5" />
              取消
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={mutation.isPending}
              className="gap-1 text-xs h-7"
            >
              <Check className="h-3.5 w-3.5" />
              保存
            </Button>
          </div>
        )}
      </div>

      {mutation.isError && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
          保存失败：{(mutation.error as Error)?.message}
        </p>
      )}

      {/* 摘要 */}
      <AnchorSection label="摘要">
        {editing ? (
          <Textarea
            value={form.summary}
            onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
            rows={5}
            className="resize-none text-sm"
            placeholder="章节摘要..."
          />
        ) : (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{anchor.summary}</p>
        )}
      </AnchorSection>

      <Separator />

      {/* 关键事件 */}
      <AnchorSection
        label="关键事件"
        icon={<Eye className="h-3.5 w-3.5" />}
        count={anchor.key_events.length}
      >
        {editing ? (
          <Textarea
            value={form.key_events}
            onChange={(e) => setForm((f) => ({ ...f, key_events: e.target.value }))}
            rows={4}
            className="resize-none font-mono text-xs"
            placeholder="每行一个事件..."
          />
        ) : anchor.key_events.length > 0 ? (
          <ul className="space-y-1.5">
            {anchor.key_events.map((event, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/60" />
                <span className="leading-relaxed">{event}</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyHint />
        )}
      </AnchorSection>

      <Separator />

      {/* 出场人物 */}
      <AnchorSection
        label="出场人物"
        icon={<Users className="h-3.5 w-3.5" />}
        count={anchor.characters_present.length}
      >
        {editing ? (
          <Textarea
            value={form.characters_present}
            onChange={(e) => setForm((f) => ({ ...f, characters_present: e.target.value }))}
            rows={3}
            className="resize-none font-mono text-xs"
            placeholder="每行一个人物名..."
          />
        ) : anchor.characters_present.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {anchor.characters_present.map((name, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
              >
                {name}
              </span>
            ))}
          </div>
        ) : (
          <EmptyHint />
        )}
      </AnchorSection>

      <Separator />

      {/* 伏笔线索 */}
      <AnchorSection label="伏笔线索" count={anchor.foreshadowing.length}>
        {editing ? (
          <Textarea
            value={form.foreshadowing}
            onChange={(e) => setForm((f) => ({ ...f, foreshadowing: e.target.value }))}
            rows={3}
            className="resize-none font-mono text-xs"
            placeholder="每行一条伏笔..."
          />
        ) : anchor.foreshadowing.length > 0 ? (
          <ul className="space-y-1.5">
            {anchor.foreshadowing.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="mt-1 shrink-0 text-amber-500">◆</span>
                <span className="leading-relaxed">{item}</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyHint />
        )}
      </AnchorSection>

      <Separator />

      {/* 主题词 */}
      <AnchorSection label="主题词" count={anchor.themes.length}>
        {editing ? (
          <Textarea
            value={form.themes}
            onChange={(e) => setForm((f) => ({ ...f, themes: e.target.value }))}
            rows={2}
            className="resize-none font-mono text-xs"
            placeholder="每行一个主题词..."
          />
        ) : anchor.themes.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {anchor.themes.map((theme, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium"
              >
                {theme}
              </span>
            ))}
          </div>
        ) : (
          <EmptyHint />
        )}
      </AnchorSection>
    </div>
  )
}

/* ─────────────────────────── 小工具组件 ─────────────────────────── */

function AnchorSection({
  label,
  icon,
  count,
  children,
}: {
  label: string
  icon?: React.ReactNode
  count?: number
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        {icon}
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        {count != null && count > 0 && (
          <span className="rounded-full bg-secondary px-1.5 py-0.5 text-xs text-muted-foreground">
            {count}
          </span>
        )}
      </div>
      {children}
    </div>
  )
}

function EmptyHint() {
  return <p className="text-sm italic text-muted-foreground">暂无数据</p>
}
