import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, CircleDashed, Info, Loader2, OctagonAlert, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { STATUS_LABEL, STATUS_TONE, type Tone } from '@/lib/format'
import type { ContentStatus, Severity } from '@/lib/types'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

const TONE_CLASS: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground border-border',
  info: 'bg-primary/10 text-primary border-primary/20',
  success: 'bg-success/12 text-success border-success/25',
  warning: 'bg-warning/12 text-warning border-warning/30',
  danger: 'bg-destructive/12 text-destructive border-destructive/25',
}

const TONE_ICON: Record<Tone, LucideIcon> = {
  neutral: CircleDashed, info: Info, success: CheckCircle2, warning: AlertTriangle, danger: OctagonAlert,
}

export function Pill({ tone = 'neutral', icon = true, children, className }: {
  tone?: Tone; icon?: boolean; children: ReactNode; className?: string
}) {
  const Icon = TONE_ICON[tone]
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap', TONE_CLASS[tone], className)}>
      {icon && <Icon className="size-3" aria-hidden />}
      {children}
    </span>
  )
}

export function StatusBadge({ status }: { status: ContentStatus }) {
  return <Pill tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Pill>
}

const SEVERITY_TONE: Record<Severity, Tone> = { low: 'neutral', medium: 'warning', high: 'danger', critical: 'danger' }

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Pill tone={SEVERITY_TONE[severity]}>{severity}</Pill>
}

export function Score({ value, min, label }: { value: number | null | undefined; min?: number; label: string }) {
  const known = typeof value === 'number'
  const pass = known && (min == null || value >= min)
  return (
    <div className="min-w-0">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className={cn('text-lg font-semibold tabular-nums', known ? (pass ? 'text-foreground' : 'text-destructive') : 'text-muted-foreground')}>
          {known ? Math.round(value) : '—'}
        </span>
        {min != null && <span className="text-xs text-muted-foreground">/ min {min}</span>}
      </div>
    </div>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function EmptyState({ icon: Icon = CircleDashed, title, children, action }: {
  icon?: LucideIcon; title: string; children?: ReactNode; action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-10 text-center">
      <Icon className="mb-3 size-8 text-muted-foreground/60" aria-hidden />
      <div className="font-medium">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-muted-foreground">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function StatCard({ label, value, hint, icon: Icon }: { label: string; value: ReactNode; hint?: ReactNode; icon?: LucideIcon }) {
  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-4">
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{label}</span>
          {Icon && <Icon className="size-4" aria-hidden />}
        </div>
        <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
        {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  )
}

export function LoadingPage() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-56" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
      </div>
      <Skeleton className="h-64" />
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn('size-4 animate-spin', className)} aria-hidden />
}

/** A Threads-style preview of one post or a connected thread. */
export function PostPreview({ posts, compact = false }: { posts: string[]; compact?: boolean }) {
  return (
    <ol className="space-y-0">
      {posts.map((post, i) => (
        <li key={i} className="relative flex gap-3">
          <div className="flex flex-col items-center">
            <div className="grid size-8 shrink-0 place-items-center rounded-full bg-primary/15 text-xs font-bold text-primary">TZ</div>
            {i < posts.length - 1 && <div className="my-1 w-px flex-1 bg-border" />}
          </div>
          <div className={cn('min-w-0 flex-1', i < posts.length - 1 && 'pb-4')}>
            <div className="flex items-center gap-2 text-sm">
              <span className="font-semibold">tektizen</span>
              {posts.length > 1 && <span className="text-xs text-muted-foreground">{i + 1}/{posts.length}</span>}
              <span className={cn('ml-auto text-xs tabular-nums', post.length > 500 ? 'text-destructive' : 'text-muted-foreground')}>
                {post.length}/500
              </span>
            </div>
            <p className={cn('mt-1 whitespace-pre-wrap break-words text-sm leading-relaxed', compact && 'line-clamp-4')}>{post}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}
