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
  created_at: string
}

export interface Message {
  id: number
  conversation_id: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  tool_calls: ToolCall[] | null
  created_at: string
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: unknown
}

export interface ModelSettings {
  provider: 'openai' | 'anthropic' | 'custom'
  api_key: string
  base_url?: string
  processing_model: string
  chat_model: string
  embedding_model: string
}

export interface ProcessingProgress {
  book_id: number
  status: ProcessingStatus
  current_chapter: number
  total_chapters: number
  message: string
}
