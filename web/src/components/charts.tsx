import type { ReactNode } from 'react'
import { BarChart3 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/common'

// Series colors come from the validated categorical palette (index.css --chart-N), in fixed order.
export const SERIES = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)']

export const AXIS = {
  tick: { fill: 'var(--muted-foreground)', fontSize: 11 },
  axisLine: false,
  tickLine: false,
} as const

export const GRID = { stroke: 'var(--border)', strokeDasharray: '0', vertical: false } as const

// Rounded data-end, anchored at the baseline.
export const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0]
export const HBAR_RADIUS: [number, number, number, number] = [0, 4, 4, 0]

export function ChartCard({ title, description, empty, emptyText, children, footer }: {
  title: string; description?: ReactNode; empty?: boolean; emptyText?: string; children: ReactNode; footer?: ReactNode
}) {
  return (
    <Card className="gap-3">
      <CardHeader>
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {description && <CardDescription className="text-xs">{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        {empty ? <EmptyState icon={BarChart3} title="No data yet">{emptyText}</EmptyState> : <div className="h-56 w-full">{children}</div>}
        {footer && !empty && <div className="mt-2 text-xs text-muted-foreground">{footer}</div>}
      </CardContent>
    </Card>
  )
}

interface TooltipPayload { name?: string; value?: number | string | null; color?: string; dataKey?: string | number }

/** Shared hover tooltip: text in ink tokens, identity carried by a color swatch. */
export function ChartTooltip({ active, payload, label, formatter }: {
  active?: boolean; payload?: TooltipPayload[]; label?: string | number; formatter?: (v: number | string | null | undefined, name?: string) => string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-md">
      {label != null && <div className="mb-1 font-medium text-popover-foreground">{label}</div>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-muted-foreground">
          <span className="size-2 rounded-sm" style={{ background: p.color }} />
          <span>{p.name}</span>
          <span className="ml-auto pl-3 font-medium tabular-nums text-popover-foreground">
            {formatter ? formatter(p.value, p.name) : p.value ?? 'n/a'}
          </span>
        </div>
      ))}
    </div>
  )
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: it.color }} /> {it.label}
        </span>
      ))}
    </div>
  )
}
