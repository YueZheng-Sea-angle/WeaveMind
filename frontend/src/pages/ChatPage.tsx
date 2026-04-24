import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare } from 'lucide-react'
import { conversationsApi, streamChat } from '@/api/conversations'
import { useChatStore } from '@/stores/chat.store'
import { useSettingsStore } from '@/stores/settings.store'
import { ConversationSidebar } from '@/components/chat/ConversationSidebar'
import { MessageBubble, StreamingMessageBubble } from '@/components/chat/MessageBubble'
import { ChatInput } from '@/components/chat/ChatInput'
import type { StreamingToolCall, SSETextData, SSEToolStartData, SSEToolEndData, SSEErrorData } from '@/types'

export function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const bookId = Number(id)
  const queryClient = useQueryClient()
  const { activeConversationId } = useChatStore()
  const chatModel = useSettingsStore((s) => s.settings.chat_model)

  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingToolCalls, setStreamingToolCalls] = useState<StreamingToolCall[]>([])
  const [streamError, setStreamError] = useState<string | null>(null)

  const bottomRef = useRef<HTMLDivElement>(null)
  const abortedRef = useRef(false)

  const { data: messages = [] } = useQuery({
    queryKey: ['messages', bookId, activeConversationId],
    queryFn: () =>
      activeConversationId
        ? conversationsApi.messages(bookId, activeConversationId)
        : Promise.resolve([]),
    enabled: !!activeConversationId,
  })

  // 消息更新时自动滚到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, streamingToolCalls.length])

  // 切换对话时清空流式状态
  useEffect(() => {
    setStreamingContent('')
    setStreamingToolCalls([])
    setStreamError(null)
    abortedRef.current = true
  }, [activeConversationId])

  const handleSend = useCallback(
    async (text: string) => {
      if (!activeConversationId || isStreaming) return

      abortedRef.current = false
      setIsStreaming(true)
      setStreamingContent('')
      setStreamingToolCalls([])
      setStreamError(null)

      try {
        for await (const sseEvent of streamChat(bookId, activeConversationId, text, chatModel)) {
          if (abortedRef.current) break

          switch (sseEvent.event) {
            case 'text': {
              const d = sseEvent.data as SSETextData
              setStreamingContent((prev) => prev + d.chunk)
              break
            }
            case 'tool_start': {
              const d = sseEvent.data as SSEToolStartData
              setStreamingToolCalls((prev) => [
                ...prev,
                { tool_name: d.tool_name, input: d.input, status: 'running' },
              ])
              break
            }
            case 'tool_end': {
              const d = sseEvent.data as SSEToolEndData
              setStreamingToolCalls((prev) =>
                prev.map((tc) =>
                  tc.tool_name === d.tool_name && tc.status === 'running'
                    ? { ...tc, output: d.output, status: 'done' }
                    : tc,
                ),
              )
              break
            }
            case 'done': {
              // 流结束，从服务端拉最新消息
              await queryClient.invalidateQueries({
                queryKey: ['messages', bookId, activeConversationId],
              })
              break
            }
            case 'error': {
              const d = sseEvent.data as SSEErrorData
              setStreamError(d.message)
              break
            }
          }
        }
      } catch (err) {
        if (!abortedRef.current) {
          setStreamError(err instanceof Error ? err.message : '连接异常，请重试')
        }
      } finally {
        if (!abortedRef.current) {
          setIsStreaming(false)
          setStreamingContent('')
          setStreamingToolCalls([])
        }
      }
    },
    [activeConversationId, bookId, chatModel, isStreaming, queryClient],
  )

  return (
    <div className="flex h-full overflow-hidden">
      <ConversationSidebar bookId={bookId} />

      <div className="flex flex-1 flex-col overflow-hidden">
        {activeConversationId ? (
          <>
            {/* 消息列表 */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
              {messages.length === 0 && !isStreaming && (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
                  <MessageSquare className="h-8 w-8 opacity-20" />
                  <p className="text-sm">向 AI 提出你的第一个问题</p>
                </div>
              )}

              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}

              {isStreaming && (
                <StreamingMessageBubble
                  content={streamingContent}
                  toolCalls={streamingToolCalls}
                />
              )}

              {streamError && (
                <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
                  {streamError}
                </div>
              )}

              <div ref={bottomRef} />
            </div>

            {/* 输入区 */}
            <ChatInput onSend={handleSend} disabled={isStreaming} />
          </>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
            <MessageSquare className="h-10 w-10 opacity-20" />
            <p className="text-sm">从左侧选择或新建一个对话</p>
          </div>
        )}
      </div>
    </div>
  )
}
