import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { List, BookText } from 'lucide-react'
import { chaptersApi } from '@/api/chapters'
import { Skeleton } from '@/components/ui/skeleton'
import type { Chapter } from '@/types'

export function ChaptersPage() {
  const { id } = useParams<{ id: string }>()
  const bookId = Number(id)
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null)

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

  const renderChapterItem = (chapter: Chapter) => {
    const isActive = chapter.id === selectedChapterId
    return (
      <button
        key={chapter.id}
        type="button"
        onClick={() => setSelectedChapterId(chapter.id)}
        className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
          isActive
            ? 'border-primary bg-primary/5'
            : 'border-border bg-card hover:bg-accent/30'
        }`}
      >
        <p className="truncate text-sm font-medium">
          第 {chapter.chapter_number} 章 {chapter.title ? `· ${chapter.title}` : ''}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{chapter.word_count} 字</p>
      </button>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-auto">
      <header className="border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold">章节结果</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">查看自动分割后的章节文本</p>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-4 overflow-hidden p-4 md:grid-cols-[280px_1fr]">
        <section className="flex flex-col overflow-hidden rounded-lg border border-border">
          <div className="border-b border-border px-3 py-2 text-sm font-medium">
            分章列表 {chapters.length > 0 ? `(${chapters.length})` : ''}
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

        <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border">
          <div className="border-b border-border px-4 py-2 text-sm font-medium">
            章节正文
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {isChapterLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
              </div>
            ) : chapterDetail ? (
              <div>
                <h2 className="mb-3 text-base font-semibold">
                  第 {chapterDetail.chapter_number} 章{' '}
                  {chapterDetail.title ? `· ${chapterDetail.title}` : ''}
                </h2>
                <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-foreground">
                  {chapterDetail.raw_text}
                </pre>
              </div>
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
                <BookText className="h-8 w-8 opacity-30" />
                <p className="text-sm">请选择一个章节查看内容</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
