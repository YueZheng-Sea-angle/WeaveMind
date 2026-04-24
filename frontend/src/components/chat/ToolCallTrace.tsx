import { useState } from 'react'
import { ChevronDown, ChevronRight, Wrench, CheckCircle2, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ToolCall, StreamingToolCall } from '@/types'

type AnyToolCall = ToolCall | StreamingToolCall

function isStreaming(tc: AnyToolCall): tc is StreamingToolCall {
  return 'tool_name' in tc
}

interface Props {
  toolCalls: AnyToolCall[]
  liveStreaming?: boolean
}

export function ToolCallTrace({ toolCalls, liveStreaming }: Props) {
  const [expanded, setExpanded] = useState(true)

  if (toolCalls.length === 0) return null

  return (
    <div className="rounded-lg border border-border/60 bg-muted/20 text-xs">
      <button
        className="flex w-full items-center gap-1.5 px-3 py-2 text-muted-foreground hover:text-foreground"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <Wrench className="h-3 w-3 shrink-0" />
        <span className="font-medium">工具调用链路</span>
        <span className="ml-auto tabular-nums text-muted-foreground/60">
          {toolCalls.length} 次
        </span>
      </button>

      {expanded && (
        <div className="border-t border-border/40 px-3 py-2 space-y-1.5">
          {toolCalls.map((tc, idx) => {
            const isLastAndLive =
              liveStreaming && idx === toolCalls.length - 1
            return (
              <ToolCallItem
                key={idx}
                toolCall={tc}
                isRunning={
                  isLastAndLive
                    ? isStreaming(tc)
                      ? tc.status === 'running'
                      : false
                    : false
                }
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

function ToolCallItem({
  toolCall,
  isRunning,
}: {
  toolCall: AnyToolCall
  isRunning: boolean
}) {
  const [showDetail, setShowDetail] = useState(false)

  const name = isStreaming(toolCall) ? toolCall.tool_name : toolCall.name
  const input = toolCall.input
  const output = toolCall.output

  return (
    <div className="rounded border border-border/40 bg-background/60">
      <button
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left"
        onClick={() => setShowDetail((v) => !v)}
      >
        {isRunning ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-blue-500" />
        ) : (
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
        )}
        <span className="flex-1 font-mono font-medium text-foreground/80">{name}</span>
        <span
          className={cn(
            'shrink-0 text-muted-foreground/50',
            showDetail && 'text-muted-foreground',
          )}
        >
          {showDetail ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
        </span>
      </button>

      {showDetail && (
        <div className="border-t border-border/30 px-2.5 py-2 space-y-2">
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
              输入
            </p>
            <pre className="overflow-x-auto rounded bg-muted/50 px-2 py-1.5 text-[11px] leading-relaxed">
              {JSON.stringify(input, null, 2)}
            </pre>
          </div>
          {output !== undefined && (
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
                输出
              </p>
              <pre className="overflow-x-auto rounded bg-muted/50 px-2 py-1.5 text-[11px] leading-relaxed whitespace-pre-wrap">
                {output.length > 400 ? `${output.slice(0, 400)}…` : output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
