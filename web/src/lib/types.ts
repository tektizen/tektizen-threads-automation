// Mirrors schemas/*.schema.json in the repository root.

export type ContentStatus =
  | 'DRAFT' | 'IDEA' | 'RESEARCH' | 'GENERATION' | 'EVALUATION' | 'REFINEMENT'
  | 'PENDING_APPROVAL' | 'READY_TO_PUBLISH' | 'PUBLISHING' | 'PUBLISHED'
  | 'PUBLISH_UNCERTAIN' | 'REJECTED' | 'FAILED' | 'ARCHIVED'

export type ContentFormat =
  | 'single' | 'thread' | 'question' | 'opinion' | 'educational'
  | 'storytelling' | 'tools_recommendation' | 'news_commentary'

export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type Confidence = 'low' | 'medium' | 'high'

export interface Draft { hook: string; body: string; cta: string; posts: string[] }

export interface Source {
  url: string; title?: string; publisher?: string; published_at?: string | null
  retrieved_at: string; summary?: string
}

export interface Fact { text: string; quote?: string; source_url: string; verified_quote?: boolean }

export interface Warning { code: string; severity: Severity; message: string; agent?: string; resolved: boolean }

export interface Stage {
  stage: string; agent: string; status: 'success' | 'failed' | 'skipped'
  started_at: string; completed_at: string | null; model: string | null
  usage: { prompt_tokens?: number | null; completion_tokens?: number | null; total_tokens?: number | null; attempts?: number } | null
  output: unknown; error: string | null
}

export interface Evaluation {
  overall_score: number | null; factuality_score: number | null; brand_score: number | null
  scores?: Record<string, number>
  fact_check_status: 'passed' | 'warnings' | 'failed' | 'not_run'
  critical_fact_failure: boolean; repetition_similarity: number | null
  warnings: Warning[]; suggestions: string[]
}

export interface ContentItem {
  id: string; created_at: string; updated_at: string; status: ContentStatus
  format: ContentFormat; topic: string; angle?: string; tone?: string; instructions?: string
  origin: 'scheduled' | 'manual_workflow' | 'studio'
  idea_id?: string | null; run_id?: string | null
  sources?: Source[]; facts?: Fact[]
  brief?: Record<string, unknown> | null
  draft: Draft | null; draft_en?: Draft | null; original_draft?: Draft | null
  versions?: { version: number; created_at: string; author: string; note?: string; draft: Draft }[]
  stages?: Stage[]
  evaluation?: Evaluation | null
  approval?: { required?: boolean; decision?: 'approved' | 'rejected' | null; decided_at?: string | null; reason?: string | null } | null
  publishing?: {
    idempotency_key?: string; zernio_post_id?: string | null; platform_post_ids?: string[]
    url?: string | null; published_at?: string | null; attempts?: number; last_error?: string | null
  } | null
  content_hash?: string | null; auto_publish?: boolean; user_notes?: string | null
}

export interface Idea {
  id: string; created_at: string; topic: string; angle?: string; rationale?: string; audience?: string
  suggested_format?: ContentFormat | null; sources?: Source[]; facts?: Fact[]
  status: 'new' | 'selected' | 'used' | 'discarded'; run_id?: string | null
}

export interface ApprovalRecord {
  id: string; created_at: string; content_id: string
  action: 'approve' | 'reject' | 'edit_approve' | 'regenerate' | 'refine' | 'archive'
  reason?: string | null; edited_posts?: string[] | null; actor?: string
  status: 'applied' | 'rejected_invalid'; error?: string | null
}

export interface PublishRecord {
  id: string; content_id: string; attempted_at: string; completed_at?: string | null
  result: 'success' | 'failed' | 'uncertain' | 'blocked' | 'duplicate'
  mode?: 'human_approved' | 'auto'; idempotency_key: string
  zernio_post_id?: string | null; platform_post_ids?: string[]; url?: string | null
  post_count?: number; http_status?: number | null; error?: string | null; run_id?: string | null
}

export type MetricKey = 'views' | 'likes' | 'replies' | 'reposts' | 'quotes' | 'shares' | 'impressions'

export interface PerformanceSnapshot {
  id: string; content_id: string; zernio_post_id?: string | null; collected_at: string
  published_at?: string | null; metrics: Partial<Record<MetricKey, number | null>>
}

export interface MemoryItem {
  id: string; text: string; confidence: Confidence; evidence_count: number
  evidence_ids?: string[]; source: 'user' | 'learning_analyst' | 'system'
  created_at: string; updated_at: string
}

export interface MemoryHistory {
  id: string; at: string; op: 'add' | 'update' | 'delete' | 'reset'; category: string
  item_id?: string | null; before?: unknown; after?: unknown; actor: string; reason?: string | null
}

export interface LearningMemory {
  schema_version: 1; updated_at: string | null; last_analysis_at?: string | null
  categories: Record<string, MemoryItem[]>; history: MemoryHistory[]
}

export interface RunRecord {
  id: string; workflow: string; github_run_id?: string | null; github_run_url?: string | null
  trigger: string; started_at: string; completed_at?: string | null; duration_ms?: number | null
  status: 'running' | 'success' | 'partial' | 'failed'; ai_requests?: number
  tokens?: { prompt?: number | null; completion?: number | null; total?: number | null }
  models?: string[]; content_ids?: string[]; errors?: string[]; warnings?: string[]
  log?: { at: string; level: 'debug' | 'info' | 'warning' | 'error'; message: string }[]
}

export interface AgentStat {
  executions: number; successes: number; failures: number
  last_execution_at?: string | null; last_status?: 'success' | 'failed' | null
  last_error?: string | null; total_tokens?: number
}

export interface Feed { name: string; url: string; enabled?: boolean; tier?: string; language?: string; ai_only?: boolean }

export interface Settings {
  schema_version: 1; updated_at: string | null
  approval: { mode: 'human_approval' | 'auto_publish'; auto_publish_enabled_at?: string | null; auto_publish_enabled_by?: string | null }
  publishing: {
    kill_switch: boolean; max_posts_per_run: number; threads_account_id?: string | null
    threads_username?: string; max_thread_posts?: number; repetition_threshold?: number
  }
  ai: {
    model: string; temperature: number; max_tokens: number; timeout_seconds: number
    max_requests_per_run: number; max_retries?: number; allow_paid_models?: boolean
    agent_models?: Record<string, string>
  }
  quality: { min_overall: number; min_factuality: number; min_brand: number; max_refinement_rounds: number }
  generation: { items_per_daily_run: number; default_tone: string; enabled_formats: ContentFormat[]; topics?: string[] }
  research: {
    feeds: Feed[]; hn_enabled?: boolean; keywords?: string[]; max_items_per_feed: number
    max_age_days: number; max_candidates?: number; fulltext_articles?: number; fulltext_max_chars?: number
  }
}

export interface Collection<T> { schema_version: 1; updated_at: string | null; items: T[] }

export interface RepoData {
  settings: Settings
  content: ContentItem[]
  ideas: Idea[]
  approvals: ApprovalRecord[]
  publishing: PublishRecord[]
  performance: PerformanceSnapshot[]
  memory: LearningMemory
  runs: RunRecord[]
  agents: Record<string, AgentStat>
}
