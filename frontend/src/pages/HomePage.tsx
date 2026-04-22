import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Upload, Trash2, Loader2, Clock } from 'lucide-react'
import { booksApi } from '@/api/books'
import { useBookStore } from '@/stores/book.store'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import type { Book } from '@/types'

const statusLabel: Record<string, string> = {
  pending: '等待处理',
  processing: '处理中',
  completed: '已完成',
  failed: '处理失败',
}

const statusVariant: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  processing: 'outline',
  completed: 'default',
  failed: 'destructive',
}

export function HomePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const setBooks = useBookStore((s) => s.setBooks)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [title, setTitle] = useState('')
  const [uploading, setUploading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const { data: books = [], isLoading } = useQuery({
    queryKey: ['books'],
    queryFn: async () => {
      const data = await booksApi.list()
      setBooks(data)
      return data
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => booksApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['books'] }),
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setSelectedFile(file)
    if (!title) setTitle(file.name.replace(/\.[^/.]+$/, ''))
  }

  const handleUpload = async () => {
    if (!selectedFile || !title.trim()) return
    setUploading(true)
    try {
      const book = await booksApi.upload(selectedFile, title.trim())
      await queryClient.invalidateQueries({ queryKey: ['books'] })
      navigate(`/books/${book.id}/processing`)
    } finally {
      setUploading(false)
      setSelectedFile(null)
      setTitle('')
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const openBook = (book: Book) => {
    if (book.processing_status === 'processing') {
      navigate(`/books/${book.id}/processing`)
    } else {
      navigate(`/books/${book.id}/chat`)
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-auto">
      <header className="border-b border-border px-6 py-4">
        <h1 className="text-xl font-semibold">书库</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">上传并分析你的长篇小说</p>
      </header>

      <div className="flex flex-1 flex-col gap-6 p-6">
        {/* Upload card */}
        <div className="rounded-lg border border-dashed border-border bg-muted/30 p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex flex-1 flex-col gap-3">
              <div>
                <label className="mb-1 block text-sm font-medium">书名</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="输入书名..."
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Markdown 文件</label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".md,.txt"
                  onChange={handleFileChange}
                  className="w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary-foreground hover:file:bg-primary/90"
                />
              </div>
            </div>
            <Button
              onClick={handleUpload}
              disabled={!selectedFile || !title.trim() || uploading}
              className="shrink-0"
            >
              {uploading ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Upload />
              )}
              上传并分析
            </Button>
          </div>
        </div>

        {/* Book list */}
        <div>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">已有书籍</h2>
          {isLoading ? (
            <div className="flex flex-col gap-2">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </div>
          ) : books.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-border py-12 text-muted-foreground">
              <BookOpen className="h-8 w-8 opacity-40" />
              <p className="text-sm">暂无书籍，上传你的第一本小说吧</p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {books.map((book) => (
                <div
                  key={book.id}
                  className="flex cursor-pointer items-center justify-between rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:bg-accent/30"
                  onClick={() => openBook(book)}
                >
                  <div className="flex items-center gap-3">
                    <BookOpen className="h-5 w-5 shrink-0 text-muted-foreground" />
                    <div>
                      <p className="font-medium">{book.title}</p>
                      <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {new Date(book.created_at).toLocaleDateString('zh-CN')}
                        {book.total_chapters != null && (
                          <span>· {book.total_chapters} 章</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={statusVariant[book.processing_status]}>
                      {statusLabel[book.processing_status]}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteMutation.mutate(book.id)
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
