import { useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@/components/ui/table'
import QueryBoundary from '@/components/QueryBoundary'
import { useCapitalControlHoldings, useCapitalControlSummary } from '@/lib/hooks'

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const pct = (v) => (v == null ? '—' : `${Number(v).toFixed(2)}%`)

export default function CapitalControl() {
  const summary = useCapitalControlSummary()
  const holdings = useCapitalControlHoldings()
  const rows = holdings.data ?? []
  const [q, setQ] = useState('')
  const [issuer, setIssuer] = useState('all')

  const issuers = useMemo(() => {
    const seen = new Map()
    rows.forEach((row) => {
      if (row.issuerId) seen.set(row.issuerId, row.issuerName || row.issuerId)
    })
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [rows])

  const filtered = useMemo(() => rows.filter((row) => {
    if (issuer !== 'all' && row.issuerId !== issuer) return false
    if (!q.trim()) return true
    const needle = q.toLowerCase()
    return [row.issuerName, row.holderReportedNameRaw, row.investorFamilyName, row.ultimateParentName]
      .some((value) => String(value || '').toLowerCase().includes(needle))
  }), [rows, issuer, q])

  const reset = () => {
    setQ('')
    setIssuer('all')
  }

  return (
    <div className="flex h-full flex-col" data-testid="capital-control-panel">
      <div className="grid grid-cols-2 gap-2 border-b border-border p-2 md:grid-cols-5">
        <Metric label="Raw observations" value={summary.data?.rawObservations ?? 0} />
        <Metric label="Effective" value={summary.data?.effectiveObservations ?? 0} />
        <Metric label="Issuers" value={summary.data?.issuers ?? 0} />
        <Metric label="Legal holders" value={summary.data?.legalHolders ?? 0} />
        <Metric label="Unresolved ties" value={summary.data?.unresolvedAmendmentTies ?? 0} warn />
      </div>

      <div className="ms-filter-bar flex items-center gap-2 p-2">
        <span className="shrink-0 text-xs text-muted-foreground">{filtered.length}</span>
        <Input
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Search issuer or investor…"
          aria-label="Search capital and control holdings"
          className="ms-filter-control h-7 flex-1 bg-background text-xs"
        />
        <select
          aria-label="Filter holdings by issuer"
          className="h-7 max-w-[220px] rounded-md border border-input bg-background px-2 text-xs"
          value={issuer}
          onChange={(event) => setIssuer(event.target.value)}
        >
          <option value="all">All issuers</option>
          {issuers.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
      </div>

      <div className="ms-scroll-region min-h-0 flex-1 overflow-auto">
        <QueryBoundary
          query={holdings}
          isEmpty={(data) => !data?.length}
          isFilteredEmpty={() => rows.length > 0 && filtered.length === 0}
          emptyLabel={summary.data?.present ? 'No effective holdings' : 'Capital/control dataset not materialized yet'}
          filteredEmptyLabel="No holdings match these filters"
          onResetFilters={reset}
        >
          <Table>
            <TableHeader className="sticky top-0 bg-card">
              <TableRow className="border-border hover:bg-transparent">
                <TableCell className="text-xs font-medium">Issuer</TableCell>
                <TableCell className="text-xs font-medium">Reported legal holder</TableCell>
                <TableCell className="text-xs font-medium">Investor family</TableCell>
                <TableCell className="text-xs font-medium">Class</TableCell>
                <TableCell className="text-right text-xs font-medium">Issuer %</TableCell>
                <TableCell className="text-right text-xs font-medium">Value</TableCell>
                <TableCell className="text-xs font-medium">As of</TableCell>
                <TableCell className="text-xs font-medium">Identity</TableCell>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((row) => (
                <TableRow key={row.observationId} className="border-border">
                  <TableCell className="max-w-[180px] truncate text-xs">{row.issuerName || row.issuerId}</TableCell>
                  <TableCell className="max-w-[220px] truncate text-xs" title={row.holderReportedNameRaw}>{row.holderReportedNameRaw}</TableCell>
                  <TableCell className="max-w-[180px] truncate text-xs text-muted-foreground">{row.investorFamilyName || '—'}</TableCell>
                  <TableCell><Badge variant="outline" className="text-[10px]">{row.positionClass || 'UNKNOWN'}</Badge></TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums">{pct(row.percentIssuer)}</TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums">{row.marketValue == null ? '—' : money.format(row.marketValue)}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{row.asOfDate || '—'}</TableCell>
                  <TableCell><Badge variant="outline" className="text-[10px]">{row.identityStatus || 'UNRESOLVED'}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </QueryBoundary>
      </div>
      <div className="border-t border-border px-3 py-2 text-[10px] text-muted-foreground">
        Legal holder, investor family, and ultimate parent are intentionally separate identity levels. Name similarity is not identity proof.
      </div>
    </div>
  )
}

function Metric({ label, value, warn = false }) {
  return (
    <div className="rounded-md border border-border bg-card/60 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={warn && value ? 'font-mono text-sm font-semibold text-destructive' : 'font-mono text-sm font-semibold'}>{value}</div>
    </div>
  )
}
