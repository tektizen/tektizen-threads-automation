import { useState } from 'react'
import { Archive, Check, PencilLine, RefreshCcw, Sparkles, X, CircleHelp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/common'
import { useCommands } from '@/lib/commands'
import { THREADS_MAX_CHARS } from '@/lib/config'
import type { ContentItem } from '@/lib/types'
import { cn } from '@/lib/utils'

type Mode = null | 'reject' | 'edit' | 'regenerate' | 'refine' | 'reconcile'

const APPROVABLE = ['PENDING_APPROVAL', 'FAILED']

export function ContentActions({ item, size = 'sm' }: { item: ContentItem; size?: 'sm' | 'default' }) {
  const { send, pendingFor } = useCommands()
  const [mode, setMode] = useState<Mode>(null)
  const [text, setText] = useState('')
  const [posts, setPosts] = useState<string[]>(item.draft?.posts ?? [])
  const [url, setUrl] = useState('')
  const pending = pendingFor(item.id)
  const status = item.status
  const critical = !!item.evaluation?.critical_fact_failure

  const open = (m: Mode) => {
    setText('')
    setPosts(item.draft?.posts ?? [''])
    setUrl(item.publishing?.url ?? '')
    setMode(m)
  }
  const run = async (label: string, cmd: Record<string, unknown>) => {
    const ok = await send(label, { content_id: item.id, ...cmd }, item.id)
    if (ok) setMode(null)
  }

  if (pending) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner /> {pending.label}: {pending.state === 'running' ? 'running in GitHub Actions…' : 'queued…'}
      </div>
    )
  }

  const canApprove = APPROVABLE.includes(status)
  const tooLong = posts.some((p) => p.length > THREADS_MAX_CHARS)

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {canApprove && (
          <Button size={size} onClick={() => run('Approve', { type: 'approve' })} disabled={critical || !item.draft}
            title={critical ? 'Critical fact-check failure: use Edit & approve to fix it first' : undefined}>
            <Check /> Approve
          </Button>
        )}
        {(canApprove || status === 'DRAFT') && item.draft && (
          <Button size={size} variant="secondary" onClick={() => open('edit')}><PencilLine /> Edit & approve</Button>
        )}
        {(canApprove || status === 'READY_TO_PUBLISH' || status === 'DRAFT') && (
          <Button size={size} variant="outline" onClick={() => open('reject')}><X /> Reject</Button>
        )}
        {(canApprove || status === 'DRAFT' || status === 'REJECTED') && item.draft && (
          <Button size={size} variant="outline" onClick={() => open('refine')}><Sparkles /> {status === 'DRAFT' ? 'Send to review' : 'Refine'}</Button>
        )}
        {!['PUBLISHED', 'PUBLISHING', 'PUBLISH_UNCERTAIN'].includes(status) && (
          <Button size={size} variant="outline" onClick={() => open('regenerate')}><RefreshCcw /> Regenerate</Button>
        )}
        {status === 'PUBLISH_UNCERTAIN' && (
          <Button size={size} variant="secondary" onClick={() => open('reconcile')}><CircleHelp /> Reconcile</Button>
        )}
        {!['ARCHIVED', 'PUBLISHING', 'PUBLISH_UNCERTAIN'].includes(status) && (
          <Button size={size} variant="ghost" onClick={() => run('Archive', { type: 'archive' })}><Archive /> Archive</Button>
        )}
      </div>

      <Dialog open={mode === 'reject'} onOpenChange={(o) => !o && setMode(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject content</DialogTitle>
            <DialogDescription>Your reason is stored as feedback and the Learning Analyst uses it to improve future drafts.</DialogDescription>
          </DialogHeader>
          <Textarea autoFocus value={text} onChange={(e) => setText(e.target.value)} rows={4}
            placeholder="cth: Terlalu formal, guna 'korang'. Hook terlalu umum." />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button>
            <Button variant="destructive" disabled={text.trim().length < 3}
              onClick={() => run('Reject', { type: 'reject', reason: text.trim() })}>Reject</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={mode === 'edit'} onOpenChange={(o) => !o && setMode(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit & approve</DialogTitle>
            <DialogDescription>
              {critical
                ? 'This draft failed fact-checking. After your edit it is re-checked automatically and only approved if it passes.'
                : 'Your edits are compared with the original draft so the system learns your editing preferences.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {posts.map((p, i) => (
              <div key={i} className="space-y-1">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Post {i + 1}</span>
                  <span className={cn('tabular-nums', p.length > THREADS_MAX_CHARS && 'text-destructive')}>{p.length}/{THREADS_MAX_CHARS}</span>
                </div>
                <Textarea value={p} rows={6} onChange={(e) => setPosts(posts.map((x, j) => (j === i ? e.target.value : x)))} />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button>
            <Button disabled={tooLong || posts.some((p) => !p.trim())}
              onClick={() => run('Edit & approve', { type: 'edit_approve', posts: posts.map((p) => p.trim()) })}>
              <Check /> Save & approve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={mode === 'regenerate' || mode === 'refine'} onOpenChange={(o) => !o && setMode(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{mode === 'regenerate' ? 'Request regeneration' : status === 'DRAFT' ? 'Send to review' : 'Send back for refinement'}</DialogTitle>
            <DialogDescription>
              {mode === 'regenerate'
                ? 'Researches and writes a new version from scratch. This item is archived and replaced.'
                : 'The Content Editor revises this draft using your notes, then it is re-evaluated and returns to the Approval Center.'}
            </DialogDescription>
          </DialogHeader>
          <Textarea autoFocus value={text} onChange={(e) => setText(e.target.value)} rows={4}
            placeholder={mode === 'regenerate' ? 'Optional: what should be different?' : 'Optional: what should the editor change?'} />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setMode(null)}>Cancel</Button>
            <Button onClick={() => mode === 'regenerate'
              ? run('Regenerate', { type: 'regenerate', reason: text.trim() || null })
              : run(status === 'DRAFT' ? 'Send to review' : 'Refine', { type: status === 'DRAFT' ? 'submit_for_review' : 'refine', reason: text.trim() || null })}>
              Send
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={mode === 'reconcile'} onOpenChange={(o) => !o && setMode(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reconcile uncertain publish</DialogTitle>
            <DialogDescription>
              The publishing request may or may not have gone through. Check @tektizen on Threads first.
              It is never retried automatically, to avoid double posting.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="rec-url">Post URL (if it is live)</Label>
            <Input id="rec-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.threads.net/@tektizen/post/…" />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => run('Mark not published', { type: 'reconcile_publish', resolution: 'not_published' })}>
              Not on Threads, publish again
            </Button>
            <Button disabled={!!url && !url.startsWith('https://')}
              onClick={() => run('Mark published', { type: 'reconcile_publish', resolution: 'published', url: url || null })}>
              It's live
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
