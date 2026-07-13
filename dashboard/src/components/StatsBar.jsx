import { useHealth, useStats } from '@/lib/hooks'
import { Database, FileText, Users, Share2 } from 'lucide-react'
import { amountsUnpopulated, AMOUNTS_NOTE } from '@/lib/cs-format'
import { cn } from '@/lib/utils'

function Kpi({ icon: Icon, label, value }) {
  return (
    <div className="flex shrink-0 items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5">
      <Icon className="h-4 w-4 text-muted-foreground" />
      <div className="leading-none">
        <div className="text-sm font-semibold text-foreground">{value}</div>
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      </div>
    </div>
  )
}

export default function StatsBar() {
  const { data: health, isLoading: healthLoading } = useHealth()
  const { data: stats } = useStats()
  const connecting = healthLoading && !health
  const up = health?.status === 'ok'
  const s = stats ?? {}

  const dot = connecting ? 'bg-amber-400' : up ? 'bg-emerald-400 animate-pulse' : 'bg-destructive'
  const label = connecting ? 'Connecting…' : up ? 'Backend online' : 'Backend down'

  return (
    <div className="panel-glass flex items-center gap-2 overflow-x-auto border-b border-border px-4 py-2">
      <div className="flex shrink-0 items-center gap-2">
        <span className={cn('inline-flex h-2.5 w-2.5 rounded-full', dot)} />
        <span className="text-sm font-medium text-foreground">{label}</span>
      </div>
      <div className="h-5 w-px shrink-0 bg-border" />
      <Kpi icon={FileText} label="Contracts" value={s.contracts ?? '–'} />
      <Kpi icon={Users} label="Entities" value={s.entities ?? '–'} />
      <Kpi icon={Share2} label="Edges" value={s.edges ?? '–'} />
      <Kpi icon={Database} label="Municipios" value={s.municipalities ?? '–'} />
      {amountsUnpopulated(stats) && (
        <span className="shrink-0 text-[11px] text-amber-300/80">{AMOUNTS_NOTE}</span>
      )}
    </div>
  )
}
