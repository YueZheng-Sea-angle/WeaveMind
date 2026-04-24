import { useState, useDeferredValue } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Search, Users, X, ChevronRight, Edit2, Check, Tag } from 'lucide-react'
import { entitiesApi } from '@/api/entities'
import type { Entity, EntityType, Relation } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

const ENTITY_TYPE_CONFIG: Record<EntityType, { label: string; className: string }> = {
  character: {
    label: '人物',
    className: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  },
  organization: {
    label: '组织',
    className: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  },
  location: {
    label: '地点',
    className: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  },
  object: {
    label: '物品',
    className: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  },
  concept: {
    label: '概念',
    className: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  },
}

const TYPE_FILTERS: Array<{ value: EntityType | 'all'; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'character', label: '人物' },
  { value: 'organization', label: '组织' },
  { value: 'location', label: '地点' },
  { value: 'object', label: '物品' },
  { value: 'concept', label: '概念' },
]

export function EntitiesPage() {
  const { id } = useParams<{ id: string }>()
  const bookId = Number(id)
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<EntityType | 'all'>('all')
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const deferredSearch = useDeferredValue(search)

  const { data: entities, isLoading } = useQuery({
    queryKey: ['entities', bookId, deferredSearch, typeFilter],
    queryFn: () =>
      entitiesApi.list(bookId, {
        q: deferredSearch || undefined,
        entity_type: typeFilter === 'all' ? undefined : typeFilter,
      }),
    enabled: Boolean(bookId),
  })

  const { data: relations } = useQuery({
    queryKey: ['relations', bookId],
    queryFn: () => entitiesApi.relations(bookId),
    enabled: Boolean(bookId),
  })

  const selectedEntity = entities?.find((e) => e.id === selectedId) ?? null

  const handleSelect = (entityId: number) => {
    setSelectedId((prev) => (prev === entityId ? null : entityId))
  }

  const handleUpdated = () => {
    queryClient.invalidateQueries({ queryKey: ['entities', bookId] })
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* 左侧：实体列表 */}
      <div
        className={cn(
          'flex flex-col border-r bg-background transition-[width] duration-200',
          selectedEntity ? 'w-[380px] min-w-[320px]' : 'flex-1',
        )}
      >
        {/* 搜索 & 类型筛选 */}
        <div className="p-4 space-y-3 border-b shrink-0">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              placeholder="搜索实体名称..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>
          <div className="flex gap-1.5 flex-wrap">
            {TYPE_FILTERS.map((t) => (
              <button
                key={t.value}
                onClick={() => setTypeFilter(t.value)}
                className={cn(
                  'px-2.5 py-1 rounded-full text-xs font-medium transition-colors',
                  typeFilter === t.value
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* 实体列表 */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 7 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : !entities?.length ? (
            <div className="flex flex-col items-center justify-center h-40 gap-2 text-muted-foreground">
              <Users className="h-8 w-8 opacity-30" />
              <p className="text-sm">
                {search || typeFilter !== 'all' ? '未找到匹配实体' : '暂无实体数据'}
              </p>
            </div>
          ) : (
            <div className="divide-y">
              {entities.map((entity) => (
                <EntityRow
                  key={entity.id}
                  entity={entity}
                  isSelected={selectedId === entity.id}
                  onClick={() => handleSelect(entity.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* 底部统计 */}
        {entities && (
          <div className="px-4 py-2 border-t text-xs text-muted-foreground shrink-0">
            共 {entities.length} 个实体
          </div>
        )}
      </div>

      {/* 右侧：实体详情面板 */}
      {selectedEntity && (
        <EntityDetailPanel
          key={selectedEntity.id}
          entity={selectedEntity}
          relations={relations}
          allEntities={entities}
          bookId={bookId}
          onClose={() => setSelectedId(null)}
          onUpdated={handleUpdated}
        />
      )}
    </div>
  )
}

/* ─────────────────────────────────── EntityRow ─────────────────────────────────── */

function EntityRow({
  entity,
  isSelected,
  onClick,
}: {
  entity: Entity
  isSelected: boolean
  onClick: () => void
}) {
  const typeConfig = ENTITY_TYPE_CONFIG[entity.type as EntityType] ?? ENTITY_TYPE_CONFIG.concept

  return (
    <button
      className={cn(
        'w-full px-4 py-3 text-left flex items-start gap-3 hover:bg-accent/60 transition-colors',
        isSelected && 'bg-accent',
      )}
      onClick={onClick}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="font-medium text-sm truncate">{entity.name}</span>
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium shrink-0',
              typeConfig.className,
            )}
          >
            {typeConfig.label}
          </span>
        </div>
        {entity.aliases.length > 0 && (
          <p className="text-xs text-muted-foreground truncate mb-0.5">
            别名：{entity.aliases.join('、')}
          </p>
        )}
        {entity.description && (
          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
            {entity.description}
          </p>
        )}
      </div>
      <ChevronRight
        className={cn(
          'h-4 w-4 text-muted-foreground mt-0.5 shrink-0 transition-transform duration-150',
          isSelected && 'rotate-90',
        )}
      />
    </button>
  )
}

/* ──────────────────────────────── EntityDetailPanel ────────────────────────────── */

interface DetailPanelProps {
  entity: Entity
  relations?: Relation[]
  allEntities?: Entity[]
  bookId: number
  onClose: () => void
  onUpdated: () => void
}

interface EditForm {
  name: string
  type: EntityType
  description: string
  aliases: string
}

function EntityDetailPanel({
  entity,
  relations,
  allEntities,
  bookId,
  onClose,
  onUpdated,
}: DetailPanelProps) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<EditForm>({
    name: entity.name,
    type: entity.type as EntityType,
    description: entity.description ?? '',
    aliases: entity.aliases.join('、'),
  })

  const mutation = useMutation({
    mutationFn: (patch: Parameters<typeof entitiesApi.update>[2]) =>
      entitiesApi.update(bookId, entity.id, patch),
    onSuccess: () => {
      setEditing(false)
      onUpdated()
    },
  })

  const handleCancel = () => {
    setForm({
      name: entity.name,
      type: entity.type as EntityType,
      description: entity.description ?? '',
      aliases: entity.aliases.join('、'),
    })
    setEditing(false)
  }

  const handleSave = () => {
    mutation.mutate({
      name: form.name || entity.name,
      type: form.type,
      description: form.description || null,
      aliases: form.aliases
        .split(/[,，、\s]+/)
        .map((a) => a.trim())
        .filter(Boolean),
    })
  }

  const typeConfig = ENTITY_TYPE_CONFIG[entity.type as EntityType] ?? ENTITY_TYPE_CONFIG.concept

  const entityRelations = relations?.filter(
    (r) => r.source_id === entity.id || r.target_id === entity.id,
  ) ?? []

  return (
    <div className="flex flex-col flex-1 overflow-hidden border-l">
      {/* 头部 */}
      <div className="flex items-center gap-2 px-5 py-4 border-b shrink-0">
        <div className="flex-1 min-w-0">
          {editing ? (
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="h-8 font-semibold"
            />
          ) : (
            <h2 className="text-base font-semibold truncate">{entity.name}</h2>
          )}
        </div>

        {!editing && (
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium shrink-0',
              typeConfig.className,
            )}
          >
            {typeConfig.label}
          </span>
        )}

        {!editing ? (
          <Button variant="ghost" size="icon" onClick={() => setEditing(true)} title="编辑">
            <Edit2 className="h-4 w-4" />
          </Button>
        ) : (
          <div className="flex gap-1 shrink-0">
            <Button variant="ghost" size="icon" onClick={handleCancel} title="取消">
              <X className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              onClick={handleSave}
              disabled={mutation.isPending}
              title="保存"
            >
              <Check className="h-4 w-4" />
            </Button>
          </div>
        )}

        <Button variant="ghost" size="icon" onClick={onClose} title="关闭">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* 正文 */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {mutation.isError && (
          <p className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
            保存失败：{(mutation.error as Error)?.message}
          </p>
        )}

        {/* 类型选择（编辑态） */}
        {editing && (
          <div className="space-y-2">
            <Label>类型</Label>
            <div className="flex gap-1.5 flex-wrap">
              {(Object.keys(ENTITY_TYPE_CONFIG) as EntityType[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setForm((f) => ({ ...f, type: t }))}
                  className={cn(
                    'px-2.5 py-1 rounded-full text-xs font-medium transition-colors border',
                    form.type === t
                      ? cn(ENTITY_TYPE_CONFIG[t].className, 'border-transparent')
                      : 'border-input bg-background hover:bg-accent',
                  )}
                >
                  {ENTITY_TYPE_CONFIG[t].label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 描述 */}
        <div className="space-y-2">
          <Label>描述</Label>
          {editing ? (
            <Textarea
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              rows={6}
              placeholder="添加实体描述..."
              className="resize-none"
            />
          ) : entity.description ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{entity.description}</p>
          ) : (
            <p className="text-sm text-muted-foreground italic">暂无描述</p>
          )}
        </div>

        <Separator />

        {/* 别名 */}
        <div className="space-y-2">
          <Label>别名</Label>
          {editing ? (
            <Input
              value={form.aliases}
              onChange={(e) => setForm((f) => ({ ...f, aliases: e.target.value }))}
              placeholder="多个别名用逗号或顿号分隔"
            />
          ) : entity.aliases.length > 0 ? (
            <div className="flex gap-1.5 flex-wrap">
              {entity.aliases.map((alias, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-0.5 text-xs"
                >
                  <Tag className="h-3 w-3 opacity-60" />
                  {alias}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground italic">无别名</p>
          )}
        </div>

        {/* 首次出现章节 */}
        {entity.first_appearance_chapter != null && (
          <>
            <Separator />
            <div className="space-y-2">
              <Label>首次出现</Label>
              <Badge variant="secondary">第 {entity.first_appearance_chapter} 章</Badge>
            </div>
          </>
        )}

        {/* 关系列表 */}
        {entityRelations.length > 0 && (
          <>
            <Separator />
            <div className="space-y-2">
              <Label>关系（{entityRelations.length}）</Label>
              <div className="space-y-2">
                {entityRelations.map((rel) => {
                  const isSource = rel.source_id === entity.id
                  const otherId = isSource ? rel.target_id : rel.source_id
                  const other = allEntities?.find((e) => e.id === otherId)
                  const otherConfig =
                    ENTITY_TYPE_CONFIG[(other?.type as EntityType) ?? 'concept']

                  return (
                    <div
                      key={rel.id}
                      className="flex items-center gap-2 text-sm rounded-lg bg-accent/40 px-3 py-2 flex-wrap"
                    >
                      <span className="font-medium shrink-0">{entity.name}</span>
                      <span className="text-xs bg-background border rounded-full px-2 py-0.5 shrink-0 text-muted-foreground">
                        {rel.relation_type}
                      </span>
                      <span className="font-medium shrink-0">
                        {other?.name ?? `#${otherId}`}
                      </span>
                      {other && (
                        <span
                          className={cn(
                            'inline-flex items-center rounded-full px-1.5 py-0.5 text-xs shrink-0',
                            otherConfig.className,
                          )}
                        >
                          {otherConfig.label}
                        </span>
                      )}
                      {rel.description && (
                        <span className="text-xs text-muted-foreground truncate">
                          — {rel.description}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/* ──────────────────────────── 小工具组件 ─────────────────────────────── */

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
      {children}
    </p>
  )
}
