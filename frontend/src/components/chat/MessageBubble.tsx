import { ToolCallTrace } from './ToolCallTrace'
import { cn } from '@/lib/utils'
import type { Message, StreamingToolCall } from '@/types'

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex w-full', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'flex max-w-[80%] flex-col gap-1',
          isUser ? 'items-end' : 'items-start',
        )}
      >
        {!isUser && message.tool_calls && message.tool_calls.length > 0 && (
          <div className="w-full min-w-[300px]">
            <ToolCallTrace toolCalls={message.tool_calls} />
          </div>
        )}

        {message.content && (
          <div
            className={cn(
              'rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
              isUser
                ? 'bg-primary text-primary-foreground rounded-tr-sm'
                : 'bg-muted text-foreground rounded-tl-sm',
            )}
          >
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          </div>
        )}
      </div>
    </div>
  )
}

interface StreamingBubbleProps {
  content: string
  toolCalls: StreamingToolCall[]
}

export function StreamingMessageBubble({ content, toolCalls }: StreamingBubbleProps) {
  const hasLiveRun = toolCalls.some((tc) => tc.status === 'running')

  return (
    <div className="flex w-full justify-start">
      <div className="flex max-w-[80%] flex-col gap-1 items-start">
        {toolCalls.length > 0 && (
          <div className="w-full min-w-[300px]">
            <ToolCallTrace toolCalls={toolCalls} liveStreaming={hasLiveRun} />
          </div>
        )}

        {content ? (
          <div className="rounded-2xl rounded-tl-sm bg-muted px-4 py-2.5 text-sm leading-relaxed text-foreground">
            <p className="whitespace-pre-wrap break-words">
              {content}
              <span className="ml-0.5 inline-block h-[1em] w-0.5 animate-pulse bg-foreground/60 align-middle" />
            </p>
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm bg-muted px-4 py-2.5 text-sm text-muted-foreground">
            <span>思考中</span>
            <span className="flex gap-0.5">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/50"
                  style={{ animationDelay: `${i * 160}ms` }}
                />
              ))}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
