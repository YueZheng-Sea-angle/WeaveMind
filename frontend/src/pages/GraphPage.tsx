import { GitFork } from 'lucide-react'

export function GraphPage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
      <GitFork className="h-10 w-10 opacity-30" />
      <p className="text-sm">知识图谱页面即将上线</p>
    </div>
  )
}
