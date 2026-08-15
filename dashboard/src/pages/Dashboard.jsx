import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@/components/ui/table'
import StatsBar from '@/components/StatsBar'
import ContractsTable from '@/components/ContractsTable'
import EntitiesTable from '@/components/EntitiesTable'
import RelationshipGraph from '@/components/RelationshipGraph'
import MunicipalityAggregates from '@/components/MunicipalityAggregates'
import CampaignFinance from '@/components/CampaignFinance'
import GovernmentChanges from '@/components/GovernmentChanges'
import ApiKeysPanel from '@/components/ApiKeysPanel'
import OwnershipDeepDive from '@/components/OwnershipDeepDive'
import QueryBoundary from '@/components/QueryBoundary'
import { useEdges, useStats } from '@/lib/hooks'
import brandMark from "@/assets/icon-64.png?inline";

// API Keys writes to a local backend .env file — no backend exists in the
// OFFLINE/standalone export, so the tab is hidden entirely there.
const OFFLINE = import.meta.env.VITE_OFFLINE === '1'

const TABS = [
  'contracts', 'entities', 'capital-control', 'government-changes', 'graph', 'municipios', 'campaign-finance',
  ...(OFFLINE ? [] : ['api-keys']),
  'ownership',
]
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const pct = (v) => (v == null ? '—' : `${Number(v).toFixed(2)}%`)

export default function Dashboard() {
  const [params, setParams] = useSearchParams()
  const tab = TABS.includes(params.get('tab')) ? params.get('tab') : 'contracts'
  const setTab = (value) => setParams((prev) => {
    prev.set('tab', value)
    return prev
  }, { replace: true })

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="panel-glass flex items-center gap-2 border-b border-border px-4 py-2.5">
        <img src={brandMark} alt="" aria-hidden="true" className="h-6 w-6 rounded-md" />
        <div>
          <h1 className="text-sm font-semibold leading-none text-foreground">moneysweep-pr</h1>
          <p className="mt-0.5 text-[11px] text-muted-foreground">Puerto Rico public-money contracts, entities, capital, campaign finance &amp; certified ownership</p>
        </div>
      </header>

      <StatsBar />

      <div className="min-h-0 flex-1 p-3">
        <Tabs value={tab} onValueChange={setTab} className="flex h-full flex-col">
          <TabsList className={`grid w-full ${OFFLINE ? 'grid-cols-8' : 'grid-cols-9'} bg-card`}>
            <TabsTrigger value="contracts" className="text-xs data-[state=active]:glow-border">Contracts</TabsTrigger>
            <TabsTrigger value="entities" className="text-xs data-[state=active]:glow-border">Entities</TabsTrigger>
            <TabsTrigger value="capital-control" className="text-xs data-[state=active]:glow-border">Capital</TabsTrigger>
            <TabsTrigger value="government-changes" className="text-xs data-[state=active]:glow-border">Gov Changes</TabsTrigger>
            <TabsTrigger value="graph" className="text-xs data-[state=active]:glow-border">Relationships</TabsTrigger>
            <TabsTrigger value="municipios" className="text-xs data-[state=active]:glow-border">Municipios</TabsTrigger>
            <TabsTrigger value="campaign-finance" className="text-xs data-[state=active]:glow-border">Campaign Finance</TabsTrigger>
            {!OFFLINE && <TabsTrigger value="api-keys" className="text-xs data-[state=active]:glow-border">API Keys</TabsTrigger>}
            <TabsTrigger value="ownership" className="text-xs data-[state=active]:glow-border">Ownership</TabsTrigger>
          </TabsList>
          <div className="mt-3 min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-background/40">
            <TabsContent value="contracts" className="m-0 h-full"><ContractsTable /></TabsContent>
            <TabsContent value="entities" className="m-0 h-full"><EntitiesTable /></TabsContent>
            <TabsContent value="capital-control" className="m-0 h-full"><CapitalControl /></TabsContent>
            <TabsContent value="government-changes" className="m-0 h-full"><GovernmentChanges /></TabsContent>
            <TabsContent value="graph" className="m-0 h-full"><RelationshipGraph /></TabsContent>
            <TabsContent value="municipios" className="m-0 h-full"><MunicipalityAggregates /></TabsContent>
            <TabsContent value="campaign-finance" className="m-0 h-full"><CampaignFinance /></TabsContent>
            {!OFFLINE && <TabsContent value="api-keys" className="m-0 h-full"><ApiKeysPanel /></TabsContent>}
            <TabsContent value="ownership" className="m-0 h-full"><OwnershipDeepDive /></TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  )
}

function CapitalControl() {
  const summaryQuery = useStats()
  const holdings = useEdges({ view: 'capital_control' })
  const rows = holdings.data ?? []
  const summary = summaryQuery.data?.capitalControl
  const [q, setQ] = useState('')
  const [issuer, setIssuer] = useState('all')
  const [identityLevel, setIdentityLevel] = useState('legal_holder')
  const [issuerB, setIssuerB] = useState('')

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

  const comparison = useMemo(() => {
    if (issuer === 'all' || !issuerB || issuer === issuerB) return null
    const field = {
      legal_holder: 'holderLegalEntityId',
      investor_family: 'investorFamilyId',
      ultimate_parent: 'ultimateParentId',
    }[identityLevel]
    const setFor = (id) => new Set(rows.filter((row) => row.issuerId === id).map((row) => row[field]).filter(Boolean))
    const a = setFor(issuer)
    const b = setFor(issuerB)
    const intersection = [...a].filter((value) => b.has(value)).sort()
    const aOnly = [...a].filter((value) => !b.has(value)).sort()
    const bOnly = [...b].filter((value) => !a.has(value)).sort()
    const union = [...new Set([...a, ...b])].sort()
    const symmetricDifference = [...aOnly, ...bOnly].sort()
    return { intersection, aOnly, bOnly, union, symmetricDifference }
  }, [rows, issuer, issuerB, identityLevel])

  const reset = () => {
    setQ('')
    setIssuer('all')
    setIssuerB('')
  }

  return (
    <div className="flex h-full flex-col" data-testid="capital-control-panel">
      <div className="grid grid-cols-2 gap-2 border-b border-border p-2 md:grid-cols-5">
        <Metric label="Raw observations" value={summary?.rawObservations ?? 0} />
        <Metric label="Effective" value={summary?.effectiveObservations ?? 0} />
        <Metric label="Issuers" value={summary?.issuers ?? 0} />
        <Metric label="Legal holders" value={summary?.legalHolders ?? 0} />
        <Metric label="Unresolved ties" value={summary?.unresolvedAmendmentTies ?? 0} warn />
      </div>

      <div className="ms-filter-bar flex flex-wrap items-center gap-2 p-2">
        <span className="shrink-0 text-xs text-muted-foreground">{filtered.length}</span>
        <Input
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Search issuer or investor…"
          aria-label="Search capital and control holdings"
          className="ms-filter-control h-7 min-w-[180px] flex-1 bg-background text-xs"
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
        <select
          aria-label="Compare against issuer"
          className="h-7 max-w-[220px] rounded-md border border-input bg-background px-2 text-xs"
          value={issuerB}
          onChange={(event) => setIssuerB(event.target.value)}
          disabled={issuer === 'all'}
        >
          <option value="">Compare issuer…</option>
          {issuers.filter(([id]) => id !== issuer).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
        <select
          aria-label="Comparison identity level"
          className="h-7 rounded-md border border-input bg-background px-2 text-xs"
          value={identityLevel}
          onChange={(event) => setIdentityLevel(event.target.value)}
        >
          <option value="legal_holder">Legal holder</option>
          <option value="investor_family">Investor family</option>
          <option value="ultimate_parent">Ultimate parent</option>
        </select>
      </div>

      {comparison && (
        <div className="grid grid-cols-5 gap-2 border-b border-border px-2 pb-2" data-testid="capital-comparison">
          <Metric label="Intersection" value={comparison.intersection.length} />
          <Metric label="A only" value={comparison.aOnly.length} />
          <Metric label="B only" value={comparison.bOnly.length} />
          <Metric label="Union" value={comparison.union.length} />
          <Metric label="Symmetric diff" value={comparison.symmetricDifference.length} />
        </div>
      )}

      <div className="ms-scroll-region min-h-0 flex-1 overflow-auto">
        <QueryBoundary
          query={holdings}
          isEmpty={(data) => !data?.length}
          isFilteredEmpty={() => rows.length > 0 && filtered.length === 0}
          emptyLabel={summary?.present ? 'No effective holdings' : 'Capital/control dataset not materialized yet'}
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
