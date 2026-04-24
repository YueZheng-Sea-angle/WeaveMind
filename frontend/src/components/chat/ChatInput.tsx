import { useRef, useState } from 'react'
import { Send } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Props {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
}

export function ChatInput({ onSend, disabled, placeholder }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value)
    const ta = e.target
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`
  }

  const canSend = !disabled && value.trim().length > 0

  return (
    <div className="flex items-end gap-2 border-t border-border bg-background px-4 py-3">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder ?? '向 AI 提问… (Enter 发送，Shift+Enter 换行)'}
        className={cn(
          'flex-1 resize-none overflow-hidden rounded-xl border border-input bg-muted/30 px-4 py-2.5 text-sm outline-none transition-colors',
          'placeholder:text-muted-foreground/60',
          'focus:border-ring focus:ring-1 focus:ring-ring/50',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
      />
      <button
        onClick={handleSend}
        disabled={!canSend}
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors',
          canSend
            ? 'bg-primary text-primary-foreground hover:bg-primary/90'
            : 'cursor-not-allowed bg-muted text-muted-foreground',
        )}
      >
        <Send className="h-4 w-4" />
      </button>
    </div>
  )
}
