export type ProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed'

export type EntityType = 'character' | 'organization' | 'location' | 'object' | 'concept'

export interface Book {
  id: number
  title: string
  processing_status: ProcessingStatus
  total_chapters: number | null
  created_at: string
}

export interface Chapter {
  id: number
  book_id: number
  chapter_number: number
  title: string | null
  raw_text: string
  word_count: number
}

export interface ChapterAnchor {
  id: number
  chapter_id: number
  summary: string
  key_events: string[]
  characters_present: string[]
  foreshadowing: string[]
  themes: string[]
}

export interface Entity {
  id: number
  book_id: number
  name: string
  aliases: string[]
  type: EntityType
  description: string | null
  attributes: Record<string, unknown>
  first_appearance_chapter: number | null
}

export interface Relation {
  id: number
  book_id: number
  source_id: number
  target_id: number
  relation_type: string
  description: string | null
  chapter_range: number[]
}

// ── 关键角色卡 ────────────────────────────────────────────────────────────────

export type CharacterCardCategory =
  | 'biography'
  | 'personality'
  | 'relationship'
  | 'skill'
  | 'item'
  | 'status'
  | 'foreshadowing'

export interface CharacterCardEntry {
  id: number
  card_id: number
  category: CharacterCardCategory
  title: string
  content: string | null
  enabled: boolean
  sort_order: number
}

export interface CharacterCard {
  id: number
  book_id: number
  entity_id: number | null
  name: string
  summary: string | null
  enabled: boolean
  entries: CharacterCardEntry[]
}

export interface Event {
  id: number
  book_id: number
  chapter_id: number
  name: string
  description: string | null
  involved_entities: number[]
  story_timestamp: string | null
}

export interface Conversation {
  id: number
  book_id: number
  title: string | null
  created_at: string
  messages: Message[]
}

export interface Message {
  id: number
  conversation_id: number
  role: 'user' | 'assistant' | 'tool'
  content: string | null
  tool_calls: ToolCall[]
  created_at: string
}

/** 与后端 tool_calls_log 格式一致：{name, input}，output 仅在流式状态中携带 */
export interface ToolCall {
  name: string
  input: Record<string, unknown>
  output?: string
}

/** 与后端 /api/settings 对齐 */
export type SettingSource = 'user' | 'env' | 'none'

/** GET /api/settings 返回的状态（敏感字段只暴露 has_xxx） */
export interface RuntimeSettings {
  openai_base_url: string
  processing_model: string
  verifier_model: string
  chat_model: string
  embedding_model: string
  embedding_base_url: string
  has_openai_key: boolean
  has_anthropic_key: boolean
  has_embedding_key: boolean
  openai_key_source: SettingSource
  anthropic_key_source: SettingSource
  openai_base_url_source: SettingSource
  embedding_key_source: SettingSource
  embedding_base_url_source: SettingSource
  user_overrides: string[]
}

/** PUT /api/settings 提交的字段（全部可选） */
export interface ModelSettingsUpdate {
  openai_api_key?: string
  openai_base_url?: string
  anthropic_api_key?: string
  processing_model?: string
  verifier_model?: string
  chat_model?: string
  embedding_model?: string
  embedding_api_key?: string
  embedding_base_url?: string
}

export interface ProcessingProgress {
  chapter_number: number
  chapter_title: string
  status: 'processing' | 'done' | 'error'
  processed: number
  total: number
}

export interface ProcessingComplete {
  processed: number
  total: number
  failed_chapters: number[]
  message: string
}

// ── SSE 事件类型（流式对话） ──────────────────────────────────────────────────

export interface SSETextData {
  chunk: string
}

export interface SSEToolStartData {
  tool_name: string
  input: Record<string, unknown>
}

export interface SSEToolEndData {
  tool_name: string
  output: string
}

export interface SSEDoneData {
  message: string
}

export interface SSEErrorData {
  message: string
}

export type SSEEventName = 'text' | 'tool_start' | 'tool_end' | 'done' | 'error'

export interface SSEEvent {
  event: SSEEventName
  data: SSETextData | SSEToolStartData | SSEToolEndData | SSEDoneData | SSEErrorData
}

/** 流式过程中实时追踪的单次工具调用状态 */
export interface StreamingToolCall {
  tool_name: string
  input: Record<string, unknown>
  output?: string
  status: 'running' | 'done'
}
