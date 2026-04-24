import { apiClient } from './client'
import type { Conversation, Message, SSEEvent } from '@/types'

export const conversationsApi = {
  list: (bookId: number) =>
    apiClient
      .get<Conversation[]>(`/books/${bookId}/conversations`)
      .then((r) => r.data),

  create: (bookId: number, title?: string) =>
    apiClient
      .post<Conversation>(`/books/${bookId}/conversations`, { title: title ?? null })
      .then((r) => r.data),

  get: (bookId: number, conversationId: number) =>
    apiClient
      .get<Conversation>(`/books/${bookId}/conversations/${conversationId}`)
      .then((r) => r.data),

  messages: (bookId: number, conversationId: number) =>
    apiClient
      .get<Message[]>(`/books/${bookId}/conversations/${conversationId}/messages`)
      .then((r) => r.data),

  delete: (bookId: number, conversationId: number) =>
    apiClient
      .delete(`/books/${bookId}/conversations/${conversationId}`)
      .then((r) => r.data),
}

/**
 * 以 AsyncGenerator 形式消费 SSE 流式聊天端点。
 * 事件类型：text / tool_start / tool_end / done / error
 */
export async function* streamChat(
  bookId: number,
  conversationId: number,
  message: string,
  model?: string,
): AsyncGenerator<SSEEvent> {
  const response = await fetch(
    `/api/books/${bookId}/conversations/${conversationId}/chat`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, model: model ?? null }),
    },
  )

  if (!response.ok) {
    throw new Error(`请求失败：HTTP ${response.status}`)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE 消息以 \n\n 分隔
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      let eventName = ''
      let eventData = ''
      for (const line of part.split('\n')) {
        if (line.startsWith('event: ')) eventName = line.slice(7).trim()
        else if (line.startsWith('data: ')) eventData = line.slice(6).trim()
      }
      if (eventName && eventData) {
        try {
          yield { event: eventName as SSEEvent['event'], data: JSON.parse(eventData) }
        } catch {
          // 忽略格式异常的帧
        }
      }
    }
  }
}
