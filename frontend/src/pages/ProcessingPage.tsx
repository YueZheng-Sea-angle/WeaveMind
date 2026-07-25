import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { CheckCircle, XCircle, Loader2, AlertTriangle, Play, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { booksApi } from '@/api/books'
import type { ProcessingProgress, ProcessingComplete } from '@/types'

interface ChapterLog {
  chapter_number: number
  chapter_title: string
  status: 'processing' | 'done' | 'error'
  error?: string
}

type PagePhase = 'idle' | 'running' | 'done'

interface ProcessingLocationState {
  autoStart?: boolean
}

export function ProcessingPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const autoStartFromUpload = Boolean(
    (location.state as ProcessingLocationState | null)?.autoStart,
  )

  const [phase, setPhase] = useState<PagePhase>(autoStartFromUpload ? 'running' : 'idle')
  const [total, setTotal] = useState<number>(0)
  const [processed, setProcessed] = useState<number>(0)
  const [chapterLogs, setChapterLogs] = useState<ChapterLog[]>([])
  const [fatalError, setFatalError] = useState<string | null>(null)
  const [failedChapters, setFailedChapters] = useState<number[]>([])

  const esRef = useRef<EventSource | null>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  const closeStream = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
  }, [])

  const startProcessing = useCallback(
    (force = false) => {
      if (!id) return
      closeStream()

      setPhase('running')
      setFatalError(null)
      setFailedChapters([])
      setChapterLogs([])
      setProcessed(0)
      setTotal(0)

      booksApi.triggerProcess(Number(id)).catch(() => {})

      const url = force
        ? `/api/books/${id}/process/stream?force=true`
        : `/api/books/${id}/process/stream`
      const es = new EventSource(url)
      esRef.current = es

      es.addEventListener('start', (e) => {
        const data = JSON.parse((e as MessageEvent).data) as { total: number; message: string }
        setTotal(data.total)
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
        setPhase('done')
        es.close()
        esRef.current = null
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
        setPhase('done')
        es.close()
        esRef.current = null
      })
    },
    [id, closeStream],
  )

  useEffect(() => {
    if (autoStartFromUpload) {
      startProcessing(false)
    }
    return () => closeStream()
  }, [autoStartFromUpload, startProcessing, closeStream])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chapterLogs])

  const done = phase === 'done'
  const running = phase === 'running'
  const percent = total > 0 ? Math.round((processed / total) * 100) : 0
  const hasPartialFailure = failedChapters.length > 0
  const isSuccess = done && !fatalError

  const handleForceReprocess = () => {
    if (
      !window.confirm(
        '将从头重新分析全书，可能覆盖已有章节锚点并改变实体合并结果。确定继续吗？',
      )
    ) {
      return
    }
    startProcessing(true)
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
      <div className="w-full max-w-xl">
        {phase === 'idle' ? (
          <div className="text-center space-y-4">
            <h2 className="text-lg font-semibold">全书分析</h2>
            <p className="text-sm text-muted-foreground leading-relaxed">
              从书库进入书籍不会自动开始分析。上传新书后会自动进入本页并开始处理；已有书籍请手动点击下方按钮。
            </p>
            <div className="flex flex-col items-center gap-2 sm:flex-row sm:justify-center">
              <Button onClick={() => startProcessing(false)} className="gap-1.5">
                <Play className="h-4 w-4" />
                开始全书分析
              </Button>
              <Button variant="outline" onClick={() => navigate(`/books/${id}/chapters`)}>
                返回章节（不分析）
              </Button>
            </div>
          </div>
        ) : (
          <>
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
                {running
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

            <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${isSuccess ? 100 : percent}%` }}
              />
            </div>

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
              {fatalError && <div className="py-0.5 text-destructive">{fatalError}</div>}
              <div ref={logsEndRef} />
            </div>

            {done && (
              <div className="mt-4 flex flex-wrap justify-center gap-3">
                {isSuccess && (
                  <Button onClick={() => navigate(`/books/${id}/chat`)}>开始对话</Button>
                )}
                <Button variant="outline" onClick={() => navigate(`/books/${id}/chapters`)}>
                  查看章节
                </Button>
                <Button
                  variant="outline"
                  onClick={handleForceReprocess}
                  className="gap-1.5 text-destructive hover:text-destructive"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  强制重新分析
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
