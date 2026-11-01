import { useEffect, useState, type ReactNode } from 'react'
import { KeyRound, Plus, ShieldAlert, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { LoadingPage, PageHeader, Pill } from '@/components/common'
import { useData, useRepo } from '@/lib/data'
import { useCommands } from '@/lib/commands'
import { checkToken, getToken, setToken, type TokenCheck } from '@/lib/github'
import { AGENTS, FORMATS, REPO, REPO_URL } from '@/lib/config'
import { fmtDateTime } from '@/lib/format'
import type { Settings as SettingsT } from '@/lib/types'

type Section = 'publishing' | 'ai' | 'quality' | 'generation' | 'research'

const ADVANCED_KEY = 'tz-settings-advanced'

function readAdvanced() {
  try {
    return localStorage.getItem(ADVANCED_KEY) === '1'
  } catch {
    return false
  }
}

export default function Settings() {
  const repo = useRepo()
  const { demo } = useData()
  const { send } = useCommands()
  const [draft, setDraft] = useState<SettingsT | null>(null)
  const [confirmAuto, setConfirmAuto] = useState(false)
  const [advanced, setAdvanced] = useState(readAdvanced)
  const toggleAdvanced = (on: boolean) => {
    setAdvanced(on)
    try {
      localStorage.setItem(ADVANCED_KEY, on ? '1' : '0')
    } catch {
      /* preference just isn't remembered */
    }
  }

  useEffect(() => {
    if (repo) setDraft(structuredClone(repo.settings))
  }, [repo])
  if (!repo || !draft) return <LoadingPage />
  const s = repo.settings
  const auto = s.approval.mode === 'auto_publish'

  const set = <K extends Section>(section: K, patch: Partial<SettingsT[K]>) =>
    setDraft({ ...draft, [section]: { ...draft[section], ...patch } })
  const dirty = (section: Section) => JSON.stringify(draft[section]) !== JSON.stringify(s[section])
  const save = (section: Section, label: string) => send(`Save ${label} settings`, { type: 'update_settings', patch: { [section]: draft[section] } })
  const num = (v: string) => (v === '' ? 0 : Number(v))

  return (
    <>
      <PageHeader title="Settings"
        description="Changes are sent as commands to GitHub Actions, validated by the engine, and committed to data/settings.json. API keys are never set here; they live in GitHub Secrets."
        actions={
          <div className="flex items-center gap-2 rounded-lg border px-3 py-2">
            <Switch id="advanced" checked={advanced} onCheckedChange={toggleAdvanced} />
            <Label htmlFor="advanced" className="text-sm">Show advanced settings</Label>
          </div>
        } />
      {!advanced && (
        <p className="-mt-3 mb-4 text-xs text-muted-foreground">AI model, news sources, and other technical options are under “Show advanced settings”.</p>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {!demo && <ConnectionCard />}

        <Card className={auto ? 'border-warning/50' : undefined}>
          <CardHeader>
            <CardTitle className="text-base">Approval mode</CardTitle>
            <CardDescription>Human approval is the default and the safe choice.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-start gap-3 rounded-lg border p-3">
              <Switch id="auto" checked={auto} onCheckedChange={(on) => on ? setConfirmAuto(true)
                : send('Switch to human approval', { type: 'update_settings', patch: { approval: { mode: 'human_approval' } } })} />
              <div className="text-sm">
                <Label htmlFor="auto" className="font-medium">Automatic publishing</Label>
                <p className="mt-1 text-muted-foreground">
                  {auto ? <>ON since {fmtDateTime(s.approval.auto_publish_enabled_at)} (by {s.approval.auto_publish_enabled_by}). Content that passes every gate publishes without review.</>
                    : 'OFF. Every post waits for your approval in the Approval Center.'}
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3 rounded-lg border border-destructive/30 p-3">
              <Switch id="kill" checked={s.publishing.kill_switch}
                onCheckedChange={(on) => send(on ? 'Activate kill switch' : 'Release kill switch', { type: 'update_settings', patch: { publishing: { kill_switch: on } } })} />
              <div className="text-sm">
                <Label htmlFor="kill" className="font-medium text-destructive">Emergency kill switch</Label>
                <p className="mt-1 text-muted-foreground">Blocks ALL publishing, including approved content, until turned off.</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <SectionCard title="Publishing" description="The Threads account itself is set in GitHub (repository variable THREADS_ACCOUNT_ID), not here." dirty={dirty('publishing')} onSave={() => save('publishing', 'publishing')}>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Username"><Input value={draft.publishing.threads_username ?? ''} onChange={(e) => set('publishing', { threads_username: e.target.value })} /></Field>
            <Field label="Max posts per run"><Input type="number" min={0} max={10} value={draft.publishing.max_posts_per_run} onChange={(e) => set('publishing', { max_posts_per_run: num(e.target.value) })} /></Field>
            <Field label="Max posts in a thread"><Input type="number" min={2} max={20} value={draft.publishing.max_thread_posts ?? 6} onChange={(e) => set('publishing', { max_thread_posts: num(e.target.value) })} /></Field>
          </div>
          {advanced && (
            <Field label="Repetition threshold" hint="Similarity (0–1) to recent posts that triggers a high-severity warning.">
              <Input type="number" step={0.05} min={0} max={1} value={draft.publishing.repetition_threshold ?? 0.6} onChange={(e) => set('publishing', { repetition_threshold: num(e.target.value) })} />
            </Field>
          )}
        </SectionCard>

        <SectionCard title="Quality thresholds" description="Internal evaluation scores required for automatic publishing. They do not guarantee engagement." dirty={dirty('quality')} onSave={() => save('quality', 'quality')}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Minimum overall score"><Input type="number" min={0} max={100} value={draft.quality.min_overall} onChange={(e) => set('quality', { min_overall: num(e.target.value) })} /></Field>
            <Field label="Minimum factuality"><Input type="number" min={0} max={100} value={draft.quality.min_factuality} onChange={(e) => set('quality', { min_factuality: num(e.target.value) })} /></Field>
            <Field label="Minimum brand compliance"><Input type="number" min={0} max={100} value={draft.quality.min_brand} onChange={(e) => set('quality', { min_brand: num(e.target.value) })} /></Field>
            <Field label="Refinement rounds" hint="Editor passes when a draft falls short (0–3)."><Input type="number" min={0} max={3} value={draft.quality.max_refinement_rounds} onChange={(e) => set('quality', { max_refinement_rounds: num(e.target.value) })} /></Field>
          </div>
        </SectionCard>

        {advanced && (
        <SectionCard title="AI model (OpenRouter)" description="Only free models are allowed. Paid models are refused by the engine." dirty={dirty('ai')} onSave={() => save('ai', 'AI')}>
          <Field label="Default model" hint="openrouter/free routes to any free model. Pin a model ending in :free for more consistent output.">
            <Input value={draft.ai.model} onChange={(e) => set('ai', { model: e.target.value.trim() })} className="font-mono" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Temperature (default)"><Input type="number" step={0.1} min={0} max={2} value={draft.ai.temperature} onChange={(e) => set('ai', { temperature: num(e.target.value) })} /></Field>
            <Field label="Max tokens per reply"><Input type="number" min={64} max={16000} value={draft.ai.max_tokens} onChange={(e) => set('ai', { max_tokens: num(e.target.value) })} /></Field>
            <Field label="Request budget per run"><Input type="number" min={1} max={100} value={draft.ai.max_requests_per_run} onChange={(e) => set('ai', { max_requests_per_run: num(e.target.value) })} /></Field>
            <Field label="Timeout (seconds)"><Input type="number" min={5} max={300} value={draft.ai.timeout_seconds} onChange={(e) => set('ai', { timeout_seconds: num(e.target.value) })} /></Field>
          </div>
          <details>
            <summary className="cursor-pointer text-sm font-medium">Per-agent model overrides</summary>
            <div className="mt-3 space-y-2">
              {AGENTS.map((a) => (
                <div key={a.id} className="grid items-center gap-2 sm:grid-cols-[10rem_1fr]">
                  <Label className="text-xs text-muted-foreground">{a.name}</Label>
                  <Input className="h-8 font-mono text-xs" placeholder={`default (${draft.ai.model})`} value={draft.ai.agent_models?.[a.id] ?? ''}
                    onChange={(e) => {
                      const next = { ...(draft.ai.agent_models ?? {}) }
                      if (e.target.value.trim()) next[a.id] = e.target.value.trim()
                      else delete next[a.id]
                      set('ai', { agent_models: next })
                    }} />
                </div>
              ))}
            </div>
          </details>
        </SectionCard>
        )}

        <SectionCard title="Generation" description="Daily runs at 08:00 Malaysia time" dirty={dirty('generation')} onSave={() => save('generation', 'generation')}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Items per daily run"><Input type="number" min={0} max={5} value={draft.generation.items_per_daily_run} onChange={(e) => set('generation', { items_per_daily_run: num(e.target.value) })} /></Field>
            <Field label="Default tone"><Input value={draft.generation.default_tone} onChange={(e) => set('generation', { default_tone: e.target.value })} /></Field>
          </div>
          <Field label="Enabled formats">
            <div className="flex flex-wrap gap-2">
              {FORMATS.map((f) => {
                const on = draft.generation.enabled_formats.includes(f.id)
                return (
                  <button key={f.id} type="button" onClick={() => set('generation', {
                    enabled_formats: on ? draft.generation.enabled_formats.filter((x) => x !== f.id) : [...draft.generation.enabled_formats, f.id] })}
                    className={`rounded-md border px-2 py-1 text-xs ${on ? 'border-primary bg-primary/10 text-foreground' : 'text-muted-foreground'}`}>
                    {f.label}
                  </button>
                )
              })}
            </div>
          </Field>
          <Field label="Focus topics" hint="One per line. Guides research and strategy.">
            <Textarea rows={5} value={(draft.generation.topics ?? []).join('\n')}
              onChange={(e) => set('generation', { topics: e.target.value.split('\n').map((t) => t.trim()).filter(Boolean) })} />
          </Field>
        </SectionCard>

        {advanced && (
        <SectionCard title="Research sources" description="Free RSS feeds + Hacker News. Full article text is extracted for the top stories." dirty={dirty('research')} onSave={() => save('research', 'research')} wide>
          <div className="space-y-2">
            {draft.research.feeds.map((f, i) => (
              <div key={i} className="grid items-center gap-2 rounded-md border p-2 sm:grid-cols-[auto_12rem_1fr_auto_auto]">
                <Switch checked={f.enabled !== false} onCheckedChange={(on) => set('research', { feeds: draft.research.feeds.map((x, j) => (j === i ? { ...x, enabled: on } : x)) })} />
                <Input className="h-8 text-sm" value={f.name} onChange={(e) => set('research', { feeds: draft.research.feeds.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
                <Input className="h-8 font-mono text-xs" value={f.url} onChange={(e) => set('research', { feeds: draft.research.feeds.map((x, j) => (j === i ? { ...x, url: e.target.value.trim() } : x)) })} />
                <div className="flex gap-1">{f.tier && <Pill icon={false}>{f.tier}</Pill>}{f.ai_only && <Pill icon={false} tone="info">AI filter</Pill>}</div>
                <Button size="icon" variant="ghost" className="size-8" aria-label="Remove feed"
                  onClick={() => set('research', { feeds: draft.research.feeds.filter((_, j) => j !== i) })}><Trash2 /></Button>
              </div>
            ))}
            <Button size="sm" variant="outline" onClick={() => set('research', { feeds: [...draft.research.feeds, { name: 'New feed', url: 'https://', enabled: true, tier: 'media', language: 'en', ai_only: true }] })}>
              <Plus /> Add feed
            </Button>
          </div>
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="Max age (days)"><Input type="number" min={1} max={30} value={draft.research.max_age_days} onChange={(e) => set('research', { max_age_days: num(e.target.value) })} /></Field>
            <Field label="Items per feed"><Input type="number" min={1} max={50} value={draft.research.max_items_per_feed} onChange={(e) => set('research', { max_items_per_feed: num(e.target.value) })} /></Field>
            <Field label="Full-text articles"><Input type="number" min={0} max={8} value={draft.research.fulltext_articles ?? 4} onChange={(e) => set('research', { fulltext_articles: num(e.target.value) })} /></Field>
            <Field label="Hacker News signal">
              <div className="flex h-9 items-center"><Switch checked={draft.research.hn_enabled !== false} onCheckedChange={(on) => set('research', { hn_enabled: on })} /></div>
            </Field>
          </div>
          <Field label="Keywords for AI filter" hint="Comma-separated. Feeds marked “AI filter” only keep items matching these.">
            <Input value={(draft.research.keywords ?? []).join(', ')} onChange={(e) => set('research', { keywords: e.target.value.split(',').map((k) => k.trim()).filter((k) => k.length >= 2) })} />
          </Field>
        </SectionCard>
        )}
      </div>

      <AlertDialog open={confirmAuto} onOpenChange={setConfirmAuto}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2"><ShieldAlert className="size-5 text-warning" /> Enable automatic publishing?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2 text-sm">
                <p>Content will be published to @{s.publishing.threads_username} <b>without your review</b> when it passes every gate:</p>
                <ul className="list-disc pl-5">
                  <li>Overall ≥ {s.quality.min_overall}, factuality ≥ {s.quality.min_factuality}, brand ≥ {s.quality.min_brand}</li>
                  <li>Fact check passed, with no critical failures and no unresolved high or critical warnings</li>
                  <li>Not a duplicate; at most {s.publishing.max_posts_per_run} post(s) per run</li>
                </ul>
                <p>Free AI models make mistakes. You can switch back or use the kill switch at any time.</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep human approval</AlertDialogCancel>
            <AlertDialogAction onClick={() => send('Enable automatic publishing', { type: 'update_settings', patch: { approval: { mode: 'auto_publish' } }, confirm_auto_publish: true })}>
              Enable automatic publishing
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

function ConnectionCard() {
  const [value, setValue] = useState('')
  const [check, setCheck] = useState<TokenCheck | null>(null)
  const [busy, setBusy] = useState(false)
  const connected = !!getToken()

  const connect = async () => {
    setBusy(true)
    const result = await checkToken(value.trim())
    setCheck(result)
    if (result.ok) {
      setToken(value.trim())
      setValue('')
    }
    setBusy(false)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base"><KeyRound className="size-4" /> GitHub connection</CardTitle>
        <CardDescription>
          Reading data needs no login (public repo). To approve, edit, or generate, connect a fine-grained token for{' '}
          <a href={REPO_URL} className="text-primary hover:underline" target="_blank" rel="noreferrer">{REPO.owner}/{REPO.name}</a>.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {connected ? (
          <div className="flex items-center gap-3">
            <Pill tone="success">Connected for this browser tab</Pill>
            <Button size="sm" variant="outline" onClick={() => { setToken(null); setCheck(null); window.location.reload() }}>Disconnect</Button>
          </div>
        ) : (
          <div className="flex gap-2">
            <Input type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} placeholder="github_pat_…" />
            <Button onClick={connect} disabled={busy || value.trim().length < 20}>Connect</Button>
          </div>
        )}
        {check && <p className={check.canDispatch ? 'text-success' : 'text-destructive'}>{check.login ? `@${check.login}: ` : ''}{check.message}</p>}
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
          <li>Token permissions: this repository only, with <b>Actions: Read and write</b> and <b>Contents: Read-only</b>.</li>
          <li>Kept in this tab's session storage only, and cleared when you close the tab. It is never part of the website code.</li>
          <li>It is sent only to api.github.com. It cannot push code; it can only start the validated workflows.</li>
        </ul>
      </CardContent>
    </Card>
  )
}

function SectionCard({ title, description, dirty, onSave, children, wide }: {
  title: string; description?: string; dirty: boolean; onSave: () => void; children: ReactNode; wide?: boolean
}) {
  return (
    <Card className={wide ? 'lg:col-span-2' : undefined}>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
      <CardFooter className="justify-end">
        <Button size="sm" onClick={onSave} disabled={!dirty}>Save {title.toLowerCase()}</Button>
      </CardFooter>
    </Card>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-sm">{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}
