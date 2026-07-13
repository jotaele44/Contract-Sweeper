import { useMemo, useState } from 'react'
import { useEdges } from '@/lib/hooks'
import QueryBoundary from '@/components/QueryBoundary'
import TypeFilterSelect from '@/components/TypeFilterSelect'
import { edgeTone, fmtMoney } from '@/lib/cs-format'
import { ArrowRight } from 'lucide-react'
import { cn } from '@/lib/utils'

// Entity relationship graph rendered as a labelled adjacency list. A list is more
// legible than a force layout at this scale and never overlaps.
export default function RelationshipGraph() {
  const query = useEdges()
  const edges = query.data ?? []
  const [type, setType] = useState('all')

  const rows = useMemo(
    () => (type === 'all' ? edges : edges.filter((e) => e.edgeType === type)),
    [edges, type],
  )

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 p-2">
        <span className="text-xs text-muted-foreground">{rows.length} relationships</span>
        <TypeFilterSelect items={edges} field="edgeType" value={type} onChange={setType} width="w-[180px]" />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <QueryBoundary query={query} isEmpty={(d) => !d?.length} emptyLabel="No relationships">
          <div className="space-y-1.5 p-2">
            {rows.map((e) => (
              <div key={e.edgeId} className="flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-2">
                <span className="flex-1 truncate text-right text-xs text-foreground">{e.sourceLabel}</span>
                <div className="flex shrink-0 flex-col items-center px-1">
                  <span className={cn('text-[9px] uppercase tracking-wide', edgeTone(e.edgeType))}>{e.edgeType}</span>
                  <ArrowRight className={cn('h-3 w-3', edgeTone(e.edgeType))} />
                  {e.amount != null && <span className="text-[9px] text-muted-foreground">{fmtMoney(e.amount)}</span>}
                </div>
                <span className="flex-1 truncate text-xs text-foreground">{e.targetLabel}</span>
              </div>
            ))}
            {rows.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">No relationships match</p>}
          </div>
        </QueryBoundary>
      </div>
    </div>
  )
}
