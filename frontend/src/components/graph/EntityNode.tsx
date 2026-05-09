import { Handle, Position } from '@xyflow/react'
import type { Node, NodeProps } from '@xyflow/react'
import type { Entity, EntityType } from '@/types'
import { cn } from '@/lib/utils'

export const ENTITY_TYPE_META: Record<
  EntityType,
  { label: string; color: string; borderColor: string; bgColor: string; badgeBg: string }
> = {
  character: {
    label: '人物',
    color: '#1d4ed8',
    borderColor: '#93c5fd',
    bgColor: '#eff6ff',
    badgeBg: '#dbeafe',
  },
  organization: {
    label: '组织',
    color: '#7c3aed',
    borderColor: '#c4b5fd',
    bgColor: '#f5f3ff',
    badgeBg: '#ede9fe',
  },
  location: {
    label: '地点',
    color: '#065f46',
    borderColor: '#6ee7b7',
    bgColor: '#ecfdf5',
    badgeBg: '#d1fae5',
  },
  object: {
    label: '物品',
    color: '#92400e',
    borderColor: '#fcd34d',
    bgColor: '#fffbeb',
    badgeBg: '#fef3c7',
  },
  concept: {
    label: '概念',
    color: '#374151',
    borderColor: '#d1d5db',
    bgColor: '#f9fafb',
    badgeBg: '#f3f4f6',
  },
}

export type EntityNodeData = { entity: Entity }
export type EntityNodeType = Node<EntityNodeData, 'entity'>

export function EntityNode({ data, selected }: NodeProps<EntityNodeType>) {
  const meta = ENTITY_TYPE_META[data.entity.type as EntityType] ?? ENTITY_TYPE_META.concept

  return (
    <div
      className={cn(
        'rounded-lg border-2 shadow-sm text-center transition-shadow duration-150',
        'w-[150px] px-3 py-2 bg-white',
        selected && 'shadow-lg',
      )}
      style={{
        borderColor: selected ? '#3b82f6' : meta.borderColor,
        backgroundColor: meta.bgColor,
        outline: selected ? '2px solid #93c3fd' : 'none',
        outlineOffset: '2px',
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: meta.borderColor, width: 8, height: 8, border: 'none' }}
      />

      <p
        className="text-sm font-semibold truncate leading-tight"
        style={{ color: meta.color }}
        title={data.entity.name}
      >
        {data.entity.name}
      </p>
      <span
        className="mt-1 inline-block text-xs rounded-full px-2 py-0.5 font-medium"
        style={{ backgroundColor: meta.badgeBg, color: meta.color }}
      >
        {meta.label}
      </span>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: meta.borderColor, width: 8, height: 8, border: 'none' }}
      />
    </div>
  )
}
