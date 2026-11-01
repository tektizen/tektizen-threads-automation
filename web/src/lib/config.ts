// Public, non-secret build-time configuration. Never put secrets in VITE_* variables:
// everything here is bundled into the public JavaScript.

export const REPO = {
  owner: import.meta.env.VITE_GITHUB_OWNER || 'tektizen',
  name: import.meta.env.VITE_GITHUB_REPO || 'tektizen-threads-automation',
  branch: import.meta.env.VITE_GITHUB_BRANCH || 'main',
}

export const REPO_URL = `https://github.com/${REPO.owner}/${REPO.name}`

export const DEMO_MODE =
  import.meta.env.VITE_DEMO_MODE === 'true' ||
  (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('demo'))

export const AGENTS = [
  { id: 'trend_researcher', name: 'Trend Researcher', role: 'Turns real news (fetched in code) into grounded ideas with verified facts.', personality: 'Curious, skeptical, precise' },
  { id: 'content_strategist', name: 'Content Strategist', role: 'Picks the idea, format, angle, and hook strategy; avoids repetition.', personality: 'Strategic, evidence-driven' },
  { id: 'content_creator', name: 'Content Creator', role: 'Writes the English master draft from the brief and verified facts.', personality: 'Direct, practical, dry humour' },
  { id: 'malay_localizer', name: 'Malay Localizer', role: 'Rewrites the draft into natural, casual Bahasa Melayu Malaysia.', personality: 'Relaxed Malaysian code-switcher' },
  { id: 'quality_evaluator', name: 'Quality Evaluator', role: 'Scores 10 criteria (0–100) and flags issues by severity.', personality: 'Exacting but constructive' },
  { id: 'fact_checker', name: 'Fact Checker', role: 'Verifies every claim against extracted facts; blocks fabrications.', personality: 'Calm, meticulous, literal' },
  { id: 'content_editor', name: 'Content Editor', role: 'Fixes flagged issues with minimal changes; leaves good work alone.', personality: 'Surgical and restrained' },
  { id: 'learning_analyst', name: 'Learning Analyst', role: 'Turns feedback and metrics into evidence-backed memory updates.', personality: 'Cautious, anti-overfitting' },
] as const

export type AgentId = (typeof AGENTS)[number]['id']

export const CONFIG_DOCS = [
  { id: 'brand_profile', name: 'Brand Profile' },
  { id: 'content_rules', name: 'Content Rules' },
  { id: 'style_examples', name: 'Style Examples' },
  { id: 'approval_policy', name: 'Approval Policy' },
] as const

export const FORMATS: { id: import('./types').ContentFormat; label: string }[] = [
  { id: 'single', label: 'Single post' },
  { id: 'thread', label: 'Thread' },
  { id: 'question', label: 'Question' },
  { id: 'opinion', label: 'Opinion' },
  { id: 'educational', label: 'Educational' },
  { id: 'storytelling', label: 'Storytelling' },
  { id: 'tools_recommendation', label: 'AI tools recommendation' },
  { id: 'news_commentary', label: 'News commentary' },
]

export const MEMORY_CATEGORIES = [
  'brand_identity', 'audience_interests', 'preferred_styles', 'successful_hooks', 'weak_hooks',
  'high_performing_topics', 'underperforming_topics', 'content_formats', 'rejection_feedback',
  'editing_patterns', 'performance_insights', 'repetition_warnings', 'strategic_recommendations',
  'lessons_learned',
] as const

export const THREADS_MAX_CHARS = 500
