import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { CheckCircle, XCircle, Loader2, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { booksApi } from '@/api/books'
import type { ProcessingProgress, ProcessingComplete } from '@/types'

interface ChapterLog {
  chapter_number: number
  chapter_title: string
  status: 'processing' | 'done' | 'error'
  error?: string
}

export function ProcessingPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [total, setTotal] = useState<number>(0)
  const [processed, setProcessed] = useState<number>(0)
  const [chapterLogs, setChapterLogs] = useState<ChapterLog[]>([])
  const [done, setDone] = useState(false)
  const [fatalError, setFatalError] = useState<string | null>(null)
  const [failedChapters, setFailedChapters] = useState<number[]>([])

  const esRef = useRef<EventSource | null>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!id) return

    // 先触发处理任务，再连接 SSE 流；忽略"已在处理中"的 409 错误
    booksApi.triggerProcess(Number(id)).catch(() => {})

    const es = new EventSource(`/api/books/${id}/process/stream`)
    esRef.current = es

    es.addEventListener('start', (e) => {
      const data = JSON.parse((e as MessageEvent).data) as { total: number; message: string }
      setTotal(data.total)
      setChapterLogs([])
    })

    es.addEventListener('progress', (e) => {
      const data = JSON.parse((e as MessageEvent).data) as ProcessingProgress
      setProcessed(data.processed)
      setTotal(data.total)
      setChapterLogs((prev) => {
        const idx = prev.findIndex((l) => l.chapter_number === data.chapter_number)
        const entry: ChapterLog = {
          chapter_number: data.chapter_number,
          chapter_title: data.chapter_title,
          status: data.status,
        }
        if (idx >= 0) {
          const next = [...prev]
          next[idx] = entry
          return next
        }
        return [...prev, entry]
      })
    })

    es.addEventListener('chapter_error', (e) => {
      const data = JSON.parse((e as MessageEvent).data) as {
        chapter_number: number
        chapter_title: string
        error: string
      }
      setChapterLogs((prev) => {
        const idx = prev.findIndex((l) => l.chapter_number === data.chapter_number)
        const entry: ChapterLog = {
          chapter_number: data.chapter_number,
          chapter_title: data.chapter_title,
          status: 'error',
          error: data.error,
        }
        if (idx >= 0) {
          const next = [...prev]
          next[idx] = entry
          return next
        }
        return [...prev, entry]
      })
    })

    es.addEventListener('complete', (e) => {
      const data = JSON.parse((e as MessageEvent).data) as ProcessingComplete
      setProcessed(data.processed)
      setFailedChapters(data.failed_chapters)
      setDone(true)
      es.close()
    })

    es.addEventListener('error', (e) => {
      const raw = (e as MessageEvent).data
      if (raw) {
        try {
          const data = JSON.parse(raw) as { message: string }
          setFatalError(data.message)
        } catch {
          setFatalError(raw)
        }
      } else {
        setFatalError('连接已断开')
      }
      setDone(true)
      es.close()
    })

    return () => es.close()
  }, [id])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chapterLogs])

  const percent = total > 0 ? Math.round((processed / total) * 100) : 0
  const hasPartialFailure = failedChapters.length > 0
  const isSuccess = done && !fatalError

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
      <div className="w-full max-w-xl">
        {/* 状态图标 */}
        <div className="mb-6 text-center">
          {!done ? (
            <Loader2 className="mx-auto h-12 w-12 animate-spin text-primary" />
          ) : fatalError ? (
            <XCircle className="mx-auto h-12 w-12 text-destructive" />
          ) : hasPartialFailure ? (
            <AlertTriangle className="mx-auto h-12 w-12 text-yellow-500" />
          ) : (
            <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
          )}

          <h2 className="mt-3 text-lg font-semibold">
            {!done
              ? '正在分析...'
              : fatalError
                ? '分析失败'
                : hasPartialFailure
                  ? `分析完成（${failedChapters.length} 章失败）`
                  : '分析完成！'}
          </h2>

          {total > 0 && (
            <p className="mt-1 text-sm text-muted-foreground">
              已处理 {processed} / {total} 章
            </p>
          )}
        </div>

        {/* 进度条 */}
        <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-secondary">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${isSuccess ? 100 : percent}%` }}
          />
        </div>

        {/* 章节处理日志 */}
        <div className="h-52 overflow-y-auto rounded-lg border border-border bg-muted/30 p-3 font-mono text-xs">
          {chapterLogs.map((log) => (
            <div
              key={log.chapter_number}
              className={`flex items-center gap-2 py-0.5 ${
                log.status === 'error'
                  ? 'text-destructive'
                  : log.status === 'done'
                    ? 'text-muted-foreground'
                    : 'text-foreground'
              }`}
            >
              <span className="w-4 shrink-0">
                {log.status === 'done' ? '✓' : log.status === 'error' ? '✗' : '…'}
              </span>
              <span>
                {log.chapter_title}
                {log.error && (
                  <span className="ml-2 text-destructive/70">{log.error}</span>
                )}
              </span>
            </div>
          ))}
          {fatalError && (
            <div className="py-0.5 text-destructive">{fatalError}</div>
          )}
          <div ref={logsEndRef} />
        </div>

        {done && (
          <div className="mt-4 flex justify-center gap-3">
            {isSuccess && (
              <Button onClick={() => navigate(`/books/${id}/chat`)}>
                开始对话
              </Button>
            )}
            <Button variant="outline" onClick={() => navigate(`/books/${id}/chapters`)}>
              查看章节
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
