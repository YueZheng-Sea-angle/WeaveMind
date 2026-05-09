import { useState, useMemo, useCallback, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  useReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  MarkerType,
  type NodeTypes,
  type NodeMouseHandler,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { GitFork, X, Tag } from 'lucide-react'

import { entitiesApi } from '@/api/entities'
import type { Entity, EntityType, Relation } from '@/types'
import {
  EntityNode,
  ENTITY_TYPE_META,
  type EntityNodeData,
} from '@/components/graph/EntityNode'
import { getLayoutedElements } from '@/lib/graph-layout'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'

const NODE_TYPES: NodeTypes = { entity: EntityNode }

const ALL_TYPES = Object.keys(ENTITY_TYPE_META) as EntityType[]

/* ─────────────────── GraphPage (Provider wrapper) ─────────────────── */

export function GraphPage() {
  const { id } = useParams<{ id: string }>()
  const bookId = Number(id)

  const { data: allEntities, isLoading: entitiesLoading } = useQuery({
    queryKey: ['entities-all', bookId],
    queryFn: () => entitiesApi.list(bookId),
    enabled: Boolean(bookId),
  })

  const { data: allRelations, isLoading: relationsLoading } = useQuery({
    queryKey: ['relations', bookId],
    queryFn: () => entitiesApi.relations(bookId),
    enabled: Boolean(bookId),
  })

  const isLoading = entitiesLoading || relationsLoading

  return (
    <ReactFlowProvider>
      <GraphCanvas
        allEntities={allEntities}
        allRelations={allRelations}
        isLoading={isLoading}
      />
    </ReactFlowProvider>
  )
}

/* ──────────────────────── GraphCanvas (inner) ──────────────────────── */

function GraphCanvas({
  allEntities,
  allRelations,
  isLoading,
}: {
  allEntities?: Entity[]
  allRelations?: Relation[]
  isLoading: boolean
}) {
  const { fitView } = useReactFlow()
  const [activeTypes, setActiveTypes] = useState<Set<EntityType>>(new Set(ALL_TYPES))
  const [selectedEntity, setSelectedEntity] = useState<Entity | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<EntityNodeData>>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

  const toggleType = useCallback((type: EntityType) => {
    setActiveTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) {
        if (next.size === 1) return prev
        next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }, [])

  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(() => {
    if (!allEntities || !allRelations) return { nodes: [], edges: [] }

    const visibleEntities = allEntities.filter((e) =>
      activeTypes.has(e.type as EntityType),
    )
    const visibleIds = new Set(visibleEntities.map((e) => e.id))

    const rawNodes: Node<EntityNodeData>[] = visibleEntities.map((e) => ({
      id: String(e.id),
      type: 'entity',
      data: { entity: e },
      position: { x: 0, y: 0 },
    }))

    const rawEdges: Edge[] = allRelations
      .filter((r) => visibleIds.has(r.source_id) && visibleIds.has(r.target_id))
      .map((r) => ({
        id: String(r.id),
        source: String(r.source_id),
        target: String(r.target_id),
        label: r.relation_type,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: '#94a3b8' },
        style: { stroke: '#94a3b8', strokeWidth: 1.5 },
        labelStyle: { fontSize: 10, fill: '#64748b', fontWeight: 500 },
        labelBgStyle: { fill: '#f8fafc', fillOpacity: 0.85 },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 4,
      }))

    if (rawNodes.length === 0) return { nodes: [], edges: [] }
    return getLayoutedElements(rawNodes, rawEdges)
  }, [allEntities, allRelations, activeTypes])

  useEffect(() => {
    setNodes(layoutedNodes as Node<EntityNodeData>[])
    setEdges(layoutedEdges)
    if (layoutedNodes.length > 0) {
      setTimeout(() => fitView({ padding: 0.12, duration: 400 }), 60)
    }
  }, [layoutedNodes, layoutedEdges, setNodes, setEdges, fitView])

  const onNodeClick: NodeMouseHandler = useCallback((_e, node) => {
    const entity = (node.data as EntityNodeData).entity
    setSelectedEntity((prev) => (prev?.id === entity.id ? null : entity))
  }, [])

  const onPaneClick = useCallback(() => {
    setSelectedEntity(null)
  }, [])

  const entityRelations = useMemo(() => {
    if (!selectedEntity || !allRelations) return []
    return allRelations.filter(
      (r) => r.source_id === selectedEntity.id || r.target_id === selectedEntity.id,
    )
  }, [selectedEntity, allRelations])

  if (isLoading) {
    return (
      <div className="flex flex-col flex-1 gap-4 p-6">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="flex-1 w-full" />
      </div>
    )
  }

  const isEmpty = !allEntities?.length

  return (
    <div className="flex flex-col h-full">
      {/* 顶部工具栏 */}
      <div className="shrink-0 flex items-center gap-3 px-4 py-2.5 border-b bg-background flex-wrap">
        <GitFork className="h-4 w-4 text-muted-foreground shrink-0" />
        <span className="text-sm font-medium text-muted-foreground shrink-0">显示类型：</span>
        <div className="flex gap-1.5 flex-wrap">
          {ALL_TYPES.map((type) => {
            const meta = ENTITY_TYPE_META[type]
            const active = activeTypes.has(type)
            return (
              <button
                key={type}
                onClick={() => toggleType(type)}
                className={cn(
                  'px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150',
                  active ? 'shadow-sm' : 'opacity-40',
                )}
                style={
                  active
                    ? {
                        backgroundColor: meta.bgColor,
                        borderColor: meta.borderColor,
                        color: meta.color,
                      }
                    : {
                        backgroundColor: 'transparent',
                        borderColor: '#d1d5db',
                        color: '#6b7280',
                      }
                }
              >
                {meta.label}
              </button>
            )
          })}
        </div>
        {allEntities && (
          <span className="ml-auto text-xs text-muted-foreground shrink-0">
            {allEntities.filter((e) => activeTypes.has(e.type as EntityType)).length} 个实体 ·{' '}
            {
              (allRelations ?? []).filter(
                (r) =>
                  activeTypes.has(
                    allEntities.find((e) => e.id === r.source_id)?.type as EntityType,
                  ) &&
                  activeTypes.has(
                    allEntities.find((e) => e.id === r.target_id)?.type as EntityType,
                  ),
              ).length
            }{' '}
            条关系
          </span>
        )}
      </div>

      {/* 画布区域 */}
      <div className="flex flex-1 overflow-hidden">
        {isEmpty ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
            <GitFork className="h-12 w-12 opacity-20" />
            <p className="text-sm">暂无实体数据，请先完成书籍处理</p>
          </div>
        ) : (
          <>
            <div className="flex-1 relative">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                nodeTypes={NODE_TYPES}
                fitView
                fitViewOptions={{ padding: 0.12 }}
                minZoom={0.1}
                maxZoom={2.5}
                nodesDraggable
                nodesConnectable={false}
                elementsSelectable
              >
                <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e2e8f0" />
                <Controls showInteractive={false} />
                <MiniMap
                  nodeColor={(n) => {
                    const entity = (n.data as EntityNodeData)?.entity
                    return entity
                      ? ENTITY_TYPE_META[entity.type as EntityType]?.borderColor ?? '#d1d5db'
                      : '#d1d5db'
                  }}
                  maskColor="rgba(248,250,252,0.7)"
                  style={{ border: '1px solid #e2e8f0', borderRadius: 8 }}
                />
              </ReactFlow>
            </div>

            {/* 实体详情侧栏 */}
            {selectedEntity && (
              <EntityDetailPanel
                entity={selectedEntity}
                relations={entityRelations}
                allEntities={allEntities}
                onClose={() => setSelectedEntity(null)}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}

/* ─────────────────────── EntityDetailPanel ─────────────────────────── */

function EntityDetailPanel({
  entity,
  relations,
  allEntities,
  onClose,
}: {
  entity: Entity
  relations: Relation[]
  allEntities?: Entity[]
  onClose: () => void
}) {
  const meta = ENTITY_TYPE_META[entity.type as EntityType] ?? ENTITY_TYPE_META.concept

  return (
    <div className="w-72 shrink-0 flex flex-col border-l bg-background overflow-hidden">
      {/* 头部 */}
      <div
        className="flex items-center gap-2 px-4 py-3 border-b shrink-0"
        style={{ borderBottomColor: meta.borderColor }}
      >
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold truncate">{entity.name}</h3>
        </div>
        <span
          className="shrink-0 text-xs font-medium rounded-full px-2 py-0.5"
          style={{ backgroundColor: meta.badgeBg, color: meta.color }}
        >
          {meta.label}
        </span>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
        {/* 描述 */}
        {entity.description ? (
          <p className="text-muted-foreground leading-relaxed text-xs">{entity.description}</p>
        ) : (
          <p className="text-muted-foreground italic text-xs">暂无描述</p>
        )}

        {/* 别名 */}
        {entity.aliases.length > 0 && (
          <>
            <Separator />
            <div className="space-y-1.5">
              <PanelLabel>别名</PanelLabel>
              <div className="flex gap-1.5 flex-wrap">
                {entity.aliases.map((alias, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
                  >
                    <Tag className="h-2.5 w-2.5 opacity-60" />
                    {alias}
                  </span>
                ))}
              </div>
            </div>
          </>
        )}

        {/* 首次出现章节 */}
        {entity.first_appearance_chapter != null && (
          <>
            <Separator />
            <div className="space-y-1.5">
              <PanelLabel>首次出现</PanelLabel>
              <span className="text-xs bg-secondary text-secondary-foreground rounded-md px-2 py-1">
                第 {entity.first_appearance_chapter} 章
              </span>
            </div>
          </>
        )}

        {/* 关系列表 */}
        {relations.length > 0 && (
          <>
            <Separator />
            <div className="space-y-2">
              <PanelLabel>关联关系（{relations.length}）</PanelLabel>
              <div className="space-y-1.5">
                {relations.map((rel) => {
                  const isSource = rel.source_id === entity.id
                  const otherId = isSource ? rel.target_id : rel.source_id
                  const other = allEntities?.find((e) => e.id === otherId)
                  const otherMeta =
                    ENTITY_TYPE_META[(other?.type as EntityType) ?? 'concept']

                  return (
                    <div
                      key={rel.id}
                      className="rounded-md bg-accent/40 px-2.5 py-2 text-xs space-y-1"
                    >
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-medium">{entity.name}</span>
                        <span className="bg-background border rounded-full px-1.5 py-0.5 text-muted-foreground text-[11px]">
                          {rel.relation_type}
                        </span>
                        <span className="font-medium">{other?.name ?? `#${otherId}`}</span>
                        {other && (
                          <span
                            className="rounded-full px-1.5 py-0.5 text-[11px] font-medium"
                            style={{
                              backgroundColor: otherMeta.badgeBg,
                              color: otherMeta.color,
                            }}
                          >
                            {otherMeta.label}
                          </span>
                        )}
                      </div>
                      {rel.description && (
                        <p className="text-muted-foreground">{rel.description}</p>
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

function PanelLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </p>
  )
}
