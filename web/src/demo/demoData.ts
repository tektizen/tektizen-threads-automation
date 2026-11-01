// DEMO DATA: used only when the dashboard runs with ?demo or VITE_DEMO_MODE=true.
// Everything here is invented sample content for previewing the interface; none of it is real.
import type { ContentItem, RepoData } from '@/lib/types'

const now = Date.now()
const ago = (hours: number) => new Date(now - hours * 3600_000).toISOString().replace(/\.\d+Z$/, 'Z')

const demoSettings: RepoData['settings'] = {
  schema_version: 1, updated_at: ago(30),
  approval: { mode: 'human_approval', auto_publish_enabled_at: null, auto_publish_enabled_by: null },
  publishing: { kill_switch: false, max_posts_per_run: 1, threads_account_id: 'demo0000000000000000demo', threads_username: 'tektizen', max_thread_posts: 6, repetition_threshold: 0.6 },
  ai: { model: 'openrouter/free', temperature: 0.7, max_tokens: 1800, timeout_seconds: 90, max_requests_per_run: 20, max_retries: 2, allow_paid_models: false, agent_models: {} },
  quality: { min_overall: 80, min_factuality: 90, min_brand: 90, max_refinement_rounds: 1 },
  generation: { items_per_daily_run: 1, default_tone: 'santai tapi berilmu', enabled_formats: ['single', 'thread', 'question', 'opinion', 'educational', 'storytelling', 'tools_recommendation', 'news_commentary'], topics: ['AI untuk pekerja pejabat', 'AI untuk pelajar'] },
  research: {
    feeds: [
      { name: 'OpenAI News', url: 'https://openai.com/news/rss.xml', tier: 'official', language: 'en', enabled: true },
      { name: 'Amanz', url: 'https://cms.amanz.my/feed/', tier: 'malaysia', language: 'ms', enabled: true, ai_only: true },
    ],
    hn_enabled: true, keywords: ['AI', 'ChatGPT', 'Gemini'], max_items_per_feed: 8, max_age_days: 7, max_candidates: 12, fulltext_articles: 4, fulltext_max_chars: 2500,
  },
}

const draft = (posts: string[], hook = posts[0].split('\n')[0]) => ({ hook, body: posts.join('\n\n').slice(hook.length).trim(), cta: posts[posts.length - 1].split('\n').pop() ?? '', posts })

function item(id: string, hoursAgo: number, partial: Partial<ContentItem>): ContentItem {
  return {
    id: `cnt_demo${id}`, created_at: ago(hoursAgo), updated_at: ago(hoursAgo - 1), status: 'PENDING_APPROVAL',
    format: 'single', topic: 'Demo topic', origin: 'scheduled', draft: null, sources: [], facts: [], versions: [], stages: [],
    evaluation: null, approval: null, publishing: null, ...partial,
  }
}

const goodEval = (overall: number, fact = 100, warnings: NonNullable<ContentItem['evaluation']>['warnings'] = []) => ({
  overall_score: overall, factuality_score: fact, brand_score: overall + 3,
  scores: { brand_compliance: overall + 3, topic_relevance: 92, hook_strength: overall - 4, specificity: overall, readability: 90, natural_language: overall + 1, audience_relevance: 90, engagement_potential: overall - 2, originality: overall - 5, cta_quality: overall - 6 },
  fact_check_status: (fact >= 90 ? 'passed' : 'warnings') as 'passed' | 'warnings', critical_fact_failure: false, repetition_similarity: 0.08, warnings,
  suggestions: ['Mulakan dengan situasi yang lebih spesifik (cth: laporan mingguan).'],
})

const stages = (model = 'demo/free-model:free') => (['research', 'strategy', 'generation', 'localization', 'code_checks', 'evaluation', 'fact_check'] as const).map((stage, i) => ({
  stage, agent: ['trend_researcher', 'content_strategist', 'content_creator', 'malay_localizer', 'code_checks', 'quality_evaluator', 'fact_checker'][i],
  status: 'success' as const, started_at: ago(26), completed_at: ago(26), model: stage === 'code_checks' ? null : model,
  usage: stage === 'code_checks' ? null : { total_tokens: 1800 + i * 120 }, output: { note: 'demo stage output' }, error: null,
}))

const content: ContentItem[] = [
  item('a1', 3, {
    topic: 'Iklan mula muncul dalam Google AI Search di Malaysia', format: 'news_commentary', angle: 'Apa maksudnya untuk peniaga kecil',
    draft: draft(['Google AI Search kat Malaysia dah mula ada iklan.\n\nMaknanya, jawapan AI yang korang baca mungkin ada slot berbayar. Untuk peniaga kecil, ini peluang baru, tapi bajet iklan pun makin bersaing.\n\nKorang rasa iklan dalam jawapan AI ni okay, atau mengganggu?']),
    evaluation: goodEval(86, 92, [{ code: 'WEAK_CTA', severity: 'medium', message: 'Soalan CTA agak umum.', agent: 'quality_evaluator', resolved: false }]),
    sources: [{ url: 'https://example.com/demo-source', title: 'Demo source article', publisher: 'Demo Publisher', published_at: ago(20), retrieved_at: ago(4) }],
    facts: [{ text: 'Ads are coming to Google AI search results in Malaysia.', quote: 'ads are coming to Google AI Search in Malaysia', source_url: 'https://example.com/demo-source', verified_quote: true }],
    stages: stages(), approval: { required: true, decision: null },
  }),
  item('a2', 5, {
    topic: '5 prompt untuk siapkan laporan mingguan', format: 'thread', origin: 'manual_workflow',
    draft: draft(['Kalau setiap Isnin korang buat report yang sama, thread ni untuk korang 🧵', 'Prompt 1: "Ringkaskan data ni dalam 5 poin untuk bos yang sibuk."', 'Prompt 2: "Cari 3 perubahan paling besar berbanding minggu lepas."', 'Report mana yang paling makan masa korang setiap minggu?']),
    evaluation: { ...goodEval(78, 74, [{ code: 'FACT_UNSUPPORTED', severity: 'high', message: 'unsupported: "jimat 3 jam seminggu" — fix: buang angka ini', agent: 'fact_checker', resolved: false }]), fact_check_status: 'warnings' },
    stages: stages(), approval: { required: true, decision: null },
  }),
  item('p1', 50, {
    topic: 'Prompt dengan konteks', format: 'educational', status: 'PUBLISHED',
    draft: draft(['Ramai guna ChatGPT macam Google. Taip soalan, dapat jawapan, habis.\n\nCuba tambah 3 benda: siapa korang, untuk siapa output tu, dan format yang korang nak.\n\nKorang selalu guna AI untuk buat apa?']),
    evaluation: goodEval(91), stages: stages(), approval: { required: true, decision: 'approved', decided_at: ago(49) },
    publishing: { zernio_post_id: 'demo1', url: 'https://www.threads.net/@tektizen', published_at: ago(48), attempts: 1 },
  }),
  item('p2', 98, {
    topic: 'Satu AI tool, guna setiap hari', format: 'opinion', status: 'PUBLISHED',
    draft: draft(['Unpopular opinion: korang tak perlu belajar 20 AI tools.\n\nPilih satu. Guna setiap hari selama sebulan.\n\nSetuju atau tak?']),
    evaluation: goodEval(88), stages: stages(), approval: { required: true, decision: 'approved', decided_at: ago(97) },
    publishing: { zernio_post_id: 'demo2', url: 'https://www.threads.net/@tektizen', published_at: ago(96), attempts: 1 },
  }),
  item('p3', 146, {
    topic: 'AI untuk pelajar SPM', format: 'thread', status: 'PUBLISHED',
    draft: draft(['Pelajar SPM: AI boleh jadi tutor, bukan mesin jawapan 🧵', 'Minta AI terangkan konsep, bukan bagi jawapan.', 'Subjek mana paling susah untuk korang?']),
    evaluation: goodEval(87), stages: stages(), approval: { required: true, decision: 'approved', decided_at: ago(145) },
    publishing: { zernio_post_id: 'demo3', url: 'https://www.threads.net/@tektizen', published_at: ago(144), attempts: 1 },
  }),
  item('r1', 120, {
    topic: 'Masa depan AI di Malaysia', format: 'opinion', status: 'REJECTED',
    draft: draft(['Dalam era digital ini, AI akan mengubah segalanya di Malaysia.']),
    evaluation: goodEval(64), approval: { required: true, decision: 'rejected', reason: 'Terlalu generik dan bunyi robotik.' },
  }),
  item('d1', 2, {
    topic: 'AI untuk freelancer: beritahu client atau tidak?', format: 'question', status: 'DRAFT', origin: 'studio',
    draft: draft(['Soalan jujur untuk freelancer:\n\nKorang pernah bagitahu client yang korang guna AI? Atau diam je?']),
  }),
]

const perf = (cid: string, hours: number, m: Partial<Record<'views' | 'likes' | 'replies' | 'shares', number>>) => ({
  id: `perf_demo${cid}`, content_id: `cnt_demo${cid}`, zernio_post_id: 'demo', collected_at: ago(hours - 30), published_at: ago(hours),
  metrics: { views: m.views ?? null, likes: m.likes ?? null, replies: m.replies ?? null, reposts: null, quotes: null, shares: m.shares ?? null, impressions: null },
})

export const demoData: RepoData = {
  settings: demoSettings,
  content,
  ideas: [
    { id: 'idea_demo00001', created_at: ago(4), topic: 'Claude halang pengguna klon permainan video', angle: 'Had etika AI yang jarang orang tahu', suggested_format: 'news_commentary', status: 'new', facts: [{ text: 'demo fact', source_url: 'https://example.com', verified_quote: true }], sources: [{ url: 'https://example.com', retrieved_at: ago(4) }] },
    { id: 'idea_demo00002', created_at: ago(4), topic: 'Korea Selatan haram calon peperiksaan yang menipu guna AI', angle: 'Pengajaran untuk pelajar Malaysia', suggested_format: 'educational', status: 'new', facts: [], sources: [] },
  ],
  approvals: [
    { id: 'apr_demo00001', created_at: ago(49), content_id: 'cnt_demop1', action: 'approve', actor: 'tektizen', status: 'applied' },
    { id: 'apr_demo00002', created_at: ago(119), content_id: 'cnt_demor1', action: 'reject', reason: 'Terlalu generik dan bunyi robotik.', actor: 'tektizen', status: 'applied' },
    { id: 'apr_demo00003', created_at: ago(97), content_id: 'cnt_demop2', action: 'edit_approve', actor: 'tektizen', status: 'applied' },
  ],
  publishing: [
    { id: 'pub_demo00001', content_id: 'cnt_demop1', attempted_at: ago(48), result: 'success', mode: 'human_approved', idempotency_key: 'tektizen-cnt_demop1-0', zernio_post_id: 'demo1', url: 'https://www.threads.net/@tektizen', post_count: 1 },
    { id: 'pub_demo00002', content_id: 'cnt_demop2', attempted_at: ago(96), result: 'success', mode: 'human_approved', idempotency_key: 'tektizen-cnt_demop2-0', zernio_post_id: 'demo2', url: 'https://www.threads.net/@tektizen', post_count: 1 },
    { id: 'pub_demo00003', content_id: 'cnt_demop3', attempted_at: ago(144), result: 'success', mode: 'human_approved', idempotency_key: 'tektizen-cnt_demop3-0', zernio_post_id: 'demo3', url: 'https://www.threads.net/@tektizen', post_count: 3 },
  ],
  performance: [perf('p1', 48, { views: 1840, likes: 62, replies: 14, shares: 5 }), perf('p2', 96, { views: 1210, likes: 35, replies: 22, shares: 2 }), perf('p3', 144, { views: 960, likes: 28, replies: 0 })],
  memory: {
    schema_version: 1, updated_at: ago(20), last_analysis_at: ago(20),
    categories: {
      rejection_feedback: [{ id: 'mem_demo00001', text: 'Owner rejects generic, robotic intros such as "Dalam era digital ini".', confidence: 'low', evidence_count: 1, source: 'learning_analyst', created_at: ago(100), updated_at: ago(100) }],
      preferred_styles: [{ id: 'mem_demo00002', text: "Use 'korang' and short lines; one idea per line on mobile.", confidence: 'high', evidence_count: 0, source: 'user', created_at: ago(200), updated_at: ago(200) }],
    },
    history: [{ id: 'mh_demo000001', at: ago(100), op: 'add', category: 'rejection_feedback', item_id: 'mem_demo00001', after: { text: 'Owner rejects generic, robotic intros such as "Dalam era digital ini".' }, actor: 'learning_analyst' }],
  },
  runs: [
    { id: 'run_demo00001', workflow: 'daily-content', trigger: 'schedule', started_at: ago(26), completed_at: ago(26), duration_ms: 142000, status: 'success', ai_requests: 7, tokens: { prompt: 14200, completion: 3900, total: 18100 }, models: ['demo/free-model:free'], log: [{ at: ago(26), level: 'info', message: 'research: 96 fetched, 12 candidates, 4 with full text' }] },
    { id: 'run_demo00002', workflow: 'publish-approved', trigger: 'workflow_dispatch', started_at: ago(48), completed_at: ago(48), duration_ms: 9000, status: 'success', ai_requests: 0, tokens: {}, log: [] },
    { id: 'run_demo00003', workflow: 'performance-analysis', trigger: 'schedule', started_at: ago(20), completed_at: ago(20), duration_ms: 31000, status: 'partial', ai_requests: 1, tokens: { total: 2100 }, warnings: ['analytics pending for 1 post'], errors: [], log: [] },
  ],
  agents: Object.fromEntries(['trend_researcher', 'content_strategist', 'content_creator', 'malay_localizer', 'quality_evaluator', 'fact_checker', 'content_editor', 'learning_analyst']
    .map((a, i) => [a, { executions: 12 - (i % 3), successes: 12 - (i % 3) - (i === 3 ? 1 : 0), failures: i === 3 ? 1 : 0, last_execution_at: ago(26), last_status: 'success' as const, total_tokens: 21000 + i * 900 }])),
}

export function demoMarkdown(path: string) {
  return `# Demo file\n\nThis is demo mode, so \`${path}\` is not loaded from GitHub.\n\n## Role\n\nDemo.\n`
}
