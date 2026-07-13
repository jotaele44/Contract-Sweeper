import { useStats } from '@/lib/hooks'
import { chartColor } from '@/lib/theme'

// Compact proportion bars for the /stats distributions the dashboard used to
// fetch and ignore (byStatus / byServiceType / byEntityType).
function Distribution({ title, data, colorIndex }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1])
  const max = entries.reduce((m, [, v]) => Math.max(m, v), 0) || 1
  const color = chartColor(colorIndex)
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <h4 className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">{title}</h4>
      {entries.length === 0 && <p className="text-xs text-muted-foreground">No data</p>}
      <div className="space-y-1.5">
        {entries.map(([label, count]) => (
          <div key={label} className="flex items-center gap-2">
            <span className="w-28 shrink-0 truncate text-xs text-foreground/80" title={label}>{label}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full" style={{ width: `${(count / max) * 100}%`, background: color }} />
            </div>
            <span className="w-8 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">{count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function StatsDistributions() {
  const { data: stats } = useStats()
  if (!stats) return null
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <Distribution title="Contracts by status" data={stats.byStatus} colorIndex={0} />
      <Distribution title="Contracts by service" data={stats.byServiceType} colorIndex={1} />
      <Distribution title="Entities by type" data={stats.byEntityType} colorIndex={2} />
    </div>
  )
}
