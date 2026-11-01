import { useMemo, useState } from 'react'
import { Lightbulb, Plus, Save, Sparkles, Trash2, Wand2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EmptyState, LoadingPage, PageHeader, Pill, StatusBadge } from '@/components/common'
import { ContentDetailSheet } from '@/components/content-detail'
import { useRepo } from '@/lib/data'
import { useCommands } from '@/lib/commands'
import { FORMATS, THREADS_MAX_CHARS } from '@/lib/config'
import { formatLabel, timeAgo } from '@/lib/format'
import type { ContentFormat, ContentItem } from '@/lib/types'
import { cn } from '@/lib/utils'

export default function Studio() {
  const repo = useRepo()
  const { generate, send } = useCommands()
  const [topic, setTopic] = useState('')
  const [format, setFormat] = useState<ContentFormat>('single')
  const [tone, setTone] = useState('')
  const [instructions, setInstructions] = useState('')
  const [posts, setPosts] = useState<string[]>([''])
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)

  const recent = useMemo(() => (repo?.content ?? [])
    .filter((c) => c.origin !== 'scheduled' || c.status === 'DRAFT')
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 12), [repo])
  const ideas = useMemo(() => (repo?.ideas ?? []).filter((i) => i.status === 'new')
    .sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 12), [repo])

  if (!repo) return <LoadingPage />
  const selectedItem = repo.content.find((c) => c.id === selected) ?? null
  const isThread = format === 'thread'
  const maxPosts = repo.settings.publishing.max_thread_posts ?? 6
  const tooLong = posts.some((p) => p.length > THREADS_MAX_CHARS)

  const runGenerate = async (overrides?: Partial<Record<'topic' | 'format' | 'instructions', string>>) => {
    const t = (overrides?.topic ?? topic).trim()
    if (!t) return
    setBusy(true)
    await generate(`Generate: ${t}`, {
      mode: 'content', topic: t, format: overrides?.format ?? format, tone: tone.trim(),
      instructions: (overrides?.instructions ?? instructions).trim(),
    })
    setBusy(false)
  }

  const saveDraft = async () => {
    setBusy(true)
    const ok = await send(`Save draft: ${topic.trim()}`, {
      type: 'save_draft', topic: topic.trim(), format, tone: tone.trim(), instructions: instructions.trim(),
      posts: posts.map((p) => p.trim()).filter(Boolean),
    })
    if (ok) setPosts([''])
    setBusy(false)
  }

  return (
    <>
      <PageHeader title="Content Studio"
        description="Generate with the AI pipeline, or write your own draft and send it through review. Generation runs in GitHub Actions and usually takes 1–3 minutes." />

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-base">Brief</CardTitle>
            <CardDescription>The same brief works for AI generation and for manual drafts.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="topic">Topic</Label>
              <Input id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="cth: Cara guna AI untuk siapkan laporan mingguan" maxLength={300} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Format</Label>
                <Select value={format} onValueChange={(v) => { setFormat(v as ContentFormat); if (v !== 'thread') setPosts((p) => [p[0] ?? '']) }}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>{FORMATS.map((f) => <SelectItem key={f.id} value={f.id}>{f.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tone">Tone</Label>
                <Input id="tone" value={tone} onChange={(e) => setTone(e.target.value)} placeholder={repo.settings.generation.default_tone} maxLength={100} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="instr">Specific instructions</Label>
              <Textarea id="instr" value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={3} maxLength={2000}
                placeholder="Optional. Personal experiences you provide here are the only ones the AI may use." />
            </div>

            <Tabs defaultValue="ai">
              <TabsList>
                <TabsTrigger value="ai"><Wand2 /> Generate with AI</TabsTrigger>
                <TabsTrigger value="manual">Write manually</TabsTrigger>
              </TabsList>
              <TabsContent value="ai" className="space-y-3 pt-2">
                <p className="text-sm text-muted-foreground">
                  Researches fresh sources on the topic, writes an English draft, localises it to BM, then evaluates and fact-checks it.
                  The result lands in the Approval Center.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => runGenerate()} disabled={busy || !topic.trim()}><Sparkles /> Generate content</Button>
                  <Button variant="outline" disabled={busy} onClick={() => generate('Research new ideas', { mode: 'ideas', topic: '', format: 'single', tone: '', instructions: '' })}>
                    <Lightbulb /> Generate ideas only
                  </Button>
                </div>
              </TabsContent>
              <TabsContent value="manual" className="space-y-3 pt-2">
                {posts.map((p, i) => (
                  <div key={i} className="space-y-1">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{isThread ? `Post ${i + 1}` : 'Post'}</span>
                      <span className="flex items-center gap-2">
                        <span className={cn('tabular-nums', p.length > THREADS_MAX_CHARS && 'text-destructive')}>{p.length}/{THREADS_MAX_CHARS}</span>
                        {isThread && posts.length > 1 && (
                          <button aria-label="Remove post" onClick={() => setPosts(posts.filter((_, j) => j !== i))}><Trash2 className="size-3.5" /></button>
                        )}
                      </span>
                    </div>
                    <Textarea value={p} rows={5} onChange={(e) => setPosts(posts.map((x, j) => (j === i ? e.target.value : x)))} />
                  </div>
                ))}
                <div className="flex flex-wrap gap-2">
                  {isThread && posts.length < maxPosts && (
                    <Button variant="outline" size="sm" onClick={() => setPosts([...posts, ''])}><Plus /> Add post</Button>
                  )}
                  <Button size="sm" onClick={saveDraft}
                    disabled={busy || !topic.trim() || tooLong || !posts.some((p) => p.trim()) || (isThread && posts.filter((p) => p.trim()).length < 2)}>
                    <Save /> Save draft
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">Saved drafts appear on the right. Open one and choose “Send to review” to run evaluation and fact-checking.</p>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          <Card className="gap-3">
            <CardHeader><CardTitle className="text-sm font-medium">Studio & manual content</CardTitle></CardHeader>
            <CardContent>
              {recent.length === 0 ? <EmptyState title="No drafts yet">Generate or write something to get started.</EmptyState> : (
                <ul className="divide-y">
                  {recent.map((c) => <ItemRow key={c.id} item={c} onOpen={() => setSelected(c.id)} />)}
                </ul>
              )}
            </CardContent>
          </Card>
          <Card className="gap-3">
            <CardHeader><CardTitle className="text-sm font-medium">Researched ideas</CardTitle></CardHeader>
            <CardContent>
              {ideas.length === 0 ? <EmptyState icon={Lightbulb} title="No unused ideas">Use “Generate ideas only” to research new ones.</EmptyState> : (
                <ul className="space-y-3">
                  {ideas.map((idea) => (
                    <li key={idea.id} className="rounded-md border p-3 text-sm">
                      <div className="font-medium">{idea.topic}</div>
                      {idea.angle && <div className="mt-0.5 text-muted-foreground">{idea.angle}</div>}
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        {idea.suggested_format && <Pill>{formatLabel(idea.suggested_format)}</Pill>}
                        <span>{idea.facts?.length ?? 0} verified facts · {idea.sources?.length ?? 0} sources · {timeAgo(idea.created_at)}</span>
                        <Button size="sm" variant="outline" className="ml-auto h-7" disabled={busy}
                          onClick={() => runGenerate({ topic: idea.topic, format: idea.suggested_format ?? 'single', instructions: idea.angle ?? '' })}>
                          <Sparkles /> Write this
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
      <ContentDetailSheet item={selectedItem} onClose={() => setSelected(null)} />
    </>
  )
}

function ItemRow({ item, onOpen }: { item: ContentItem; onOpen: () => void }) {
  return (
    <li>
      <button onClick={onOpen} className="w-full py-2.5 text-left">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{item.topic}</span>
          <span className="ml-auto shrink-0"><StatusBadge status={item.status} /></span>
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground">{formatLabel(item.format)} · {timeAgo(item.updated_at)}</div>
      </button>
    </li>
  )
}
