import { Link, NavLink, Outlet, useParams } from 'react-router-dom'
import {
  BookOpen,
  MessageSquare,
  List,
  Users,
  GitFork,
  Settings,
  ChevronLeft,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useBookStore } from '@/stores/book.store'

const bookNavItems = [
  { to: 'chat', label: '对话', icon: MessageSquare },
  { to: 'chapters', label: '章节', icon: List },
  { to: 'entities', label: '实体', icon: Users },
  { to: 'graph', label: '图谱', icon: GitFork },
  { to: 'settings', label: '设置', icon: Settings },
]

export function AppLayout() {
  const { id } = useParams<{ id: string }>()
  const currentBook = useBookStore((s) => s.currentBook)

  return (
    <div className="flex h-screen bg-background">
      <aside className="flex w-56 flex-col border-r border-border bg-sidebar-background">
        <div className="flex h-14 items-center gap-2 border-b border-sidebar-border px-4">
          <BookOpen className="h-5 w-5 text-sidebar-primary" />
          <span className="font-semibold text-sidebar-foreground">WeaveMind</span>
        </div>

        <div className="flex flex-1 flex-col gap-1 overflow-y-auto p-2">
          {id ? (
            <>
              <Link
                to="/"
                className="mb-2 flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs text-sidebar-foreground/60 hover:text-sidebar-foreground"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                返回书库
              </Link>
              {currentBook && (
                <p className="truncate px-3 py-1 text-sm font-medium text-sidebar-foreground">
                  {currentBook.title}
                </p>
              )}
              <div className="mt-1 flex flex-col gap-0.5">
                {bookNavItems.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={`/books/${id}/${to}`}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors',
                        isActive
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                          : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
                      )
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {label}
                  </NavLink>
                ))}
              </div>
            </>
          ) : (
            <NavLink
              to="/"
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
                )
              }
            >
              <BookOpen className="h-4 w-4 shrink-0" />
              书库
            </NavLink>
          )}
        </div>
      </aside>

      <main className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
