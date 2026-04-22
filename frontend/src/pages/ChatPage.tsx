import { MessageSquare } from 'lucide-react'

export function ChatPage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
      <MessageSquare className="h-10 w-10 opacity-30" />
      <p className="text-sm">对话功能即将上线</p>
    </div>
  )
}
