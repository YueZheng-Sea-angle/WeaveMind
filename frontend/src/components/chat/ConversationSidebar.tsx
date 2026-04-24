import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Plus, Trash2 } from 'lucide-react'
import { conversationsApi } from '@/api/conversations'
import { useChatStore } from '@/stores/chat.store'
import { cn } from '@/lib/utils'
import type { Conversation } from '@/types'

interface Props {
  bookId: number
}

export function ConversationSidebar({ bookId }: Props) {
  const queryClient = useQueryClient()
  const { activeConversationId, setActiveConversationId } = useChatStore()

  const { data: conversations = [] } = useQuery({
    queryKey: ['conversations', bookId],
    queryFn: () => conversationsApi.list(bookId),
  })

  const createMutation = useMutation({
    mutationFn: () => conversationsApi.create(bookId),
    onSuccess: (conv) => {
      queryClient.invalidateQueries({ queryKey: ['conversations', bookId] })
      setActiveConversationId(conv.id)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (convId: number) => conversationsApi.delete(bookId, convId),
    onSuccess: (_data, convId) => {
      queryClient.invalidateQueries({ queryKey: ['conversations', bookId] })
      if (activeConversationId === convId) {
        setActiveConversationId(null)
      }
    },
  })

  return (
    <div className="flex h-full w-52 shrink-0 flex-col border-r border-border">
      <div className="flex items-center justify-between border-b border-border px-3 py-3">
        <span className="text-sm font-medium text-foreground">对话历史</span>
        <button
          className={cn(
            'flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
            createMutation.isPending && 'cursor-not-allowed opacity-50',
          )}
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          title="新建对话"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {conversations.length === 0 && (
          <p className="py-10 text-center text-xs text-muted-foreground">
            点击 + 开始新对话
          </p>
        )}
        {[...conversations].reverse().map((conv, idx) => (
          <ConversationItem
            key={conv.id}
            conv={conv}
            index={conversations.length - idx}
            isActive={conv.id === activeConversationId}
            onSelect={() => setActiveConversationId(conv.id)}
            onDelete={() => deleteMutation.mutate(conv.id)}
          />
        ))}
      </div>
    </div>
  )
}

function ConversationItem({
  conv,
  index,
  isActive,
  onSelect,
  onDelete,
}: {
  conv: Conversation
  index: number
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  return (
    <div
      className={cn(
        'group flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-sm transition-colors',
        isActive
          ? 'bg-accent text-accent-foreground'
          : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
      )}
      onClick={onSelect}
    >
      <MessageSquare className="h-3.5 w-3.5 shrink-0" />
      <span className="flex-1 truncate text-xs">
        {conv.title ?? `对话 #${index}`}
      </span>
      <button
        className="invisible h-4 w-4 shrink-0 rounded text-muted-foreground/60 hover:text-destructive group-hover:visible"
        onClick={(e) => {
          e.stopPropagation()
          onDelete()
        }}
        title="删除对话"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  )
}
