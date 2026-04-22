import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { CheckCircle, XCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { ProcessingProgress } from '@/types'

export function ProcessingPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [progress, setProgress] = useState<ProcessingProgress | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!id) return
    const es = new EventSource(`/api/books/${id}/process/stream`)
    esRef.current = es

    es.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data) as ProcessingProgress
      setProgress(data)
      setLogs((prev) => [...prev, data.message])
    })

    es.addEventListener('done', () => {
      setDone(true)
      es.close()
    })

    es.addEventListener('error', (e) => {
      const msg = (e as MessageEvent).data ?? '处理失败'
      setError(msg)
      setDone(true)
      es.close()
    })

    return () => es.close()
  }, [id])

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const percent =
    progress && progress.total_chapters > 0
      ? Math.round((progress.current_chapter / progress.total_chapters) * 100)
      : 0

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
      <div className="w-full max-w-xl">
        <div className="mb-6 text-center">
          {done && !error ? (
            <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
          ) : error ? (
            <XCircle className="mx-auto h-12 w-12 text-destructive" />
          ) : (
            <Loader2 className="mx-auto h-12 w-12 animate-spin text-primary" />
          )}
          <h2 className="mt-3 text-lg font-semibold">
            {done && !error ? '分析完成！' : error ? '分析失败' : '正在分析...'}
          </h2>
          {progress && (
            <p className="mt-1 text-sm text-muted-foreground">
              第 {progress.current_chapter} / {progress.total_chapters} 章
            </p>
          )}
        </div>

        {/* Progress bar */}
        <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-secondary">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${done && !error ? 100 : percent}%` }}
          />
        </div>

        {/* Logs */}
        <div className="h-48 overflow-y-auto rounded-lg border border-border bg-muted/30 p-3 font-mono text-xs">
          {logs.map((log, i) => (
            <div key={i} className="py-0.5 text-muted-foreground">
              {log}
            </div>
          ))}
          {error && <div className="py-0.5 text-destructive">{error}</div>}
          <div ref={logsEndRef} />
        </div>

        {done && (
          <div className="mt-4 flex justify-center">
            <Button onClick={() => navigate(`/books/${id}/chat`)}>
              开始对话
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
