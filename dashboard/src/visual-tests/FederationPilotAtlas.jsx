import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource-variable/inter'
import '@fontsource/jetbrains-mono'
import '@/index.css'
import '@pr-federation/react/styles.css'
import '@/styles/pilot.css'
import '@/styles/federation-pilot-atlas.css'
import QueryBoundary from '@/components/QueryBoundary'
import {
  FederationStatCard,
  FederationStatusBadge,
} from '@pr-federation/react'
import { Database, FileText } from 'lucide-react'

const params = new URLSearchParams(window.location.search)
document.documentElement.dataset.repo = 'moneysweep-pr'
document.documentElement.dataset.theme = params.get('theme') === 'light' ? 'light' : 'dark'

const FIXTURE_UPDATED_AT = Date.now()
const records = [{ id: 'contract-1' }]
const baseQuery = {
  data: records,
  dataUpdatedAt: FIXTURE_UPDATED_AT,
  error: null,
  fetchStatus: 'idle',
  isError: false,
  isFetching: false,
  isLoading: false,
  isPending: false,
  isStale: false,
  refetch: () => Promise.resolve(),
}
const query = (overrides) => ({ ...baseQuery, ...overrides })
const isEmpty = (data) => !data?.length

function StateCard({ state, title, children }) {
  return (
    <section className="atlas-card fd-panel" data-state-card={state}>
      <h2>{title}</h2>
      {children}
    </section>
  )
}

function CachedRows() {
  return <p className="atlas-cached-data">Cached contract rows remain visible.</p>
}

function Atlas() {
  return (
    <main className="atlas-shell">
      <header className="atlas-header">
        <div>
          <p className="atlas-kicker">MoneySweep pilot · immutable RC</p>
          <h1>Federation async-state and primitive atlas</h1>
          <p>Runtime QueryBoundary states with shared buttons, panels, stat cards, and semantic-badge contracts.</p>
        </div>
        <div className="atlas-badges" aria-label="Operational semantic badge examples">
          <FederationStatusBadge kind="operational" status="operational" />
          <FederationStatusBadge kind="operational" status="degraded" />
          <FederationStatusBadge kind="operational" status="critical" />
          <FederationStatusBadge kind="operational" status="offline" />
        </div>
      </header>

      <section className="atlas-stats" aria-label="Shared statistic card examples">
        <FederationStatCard label="Contracts" value="2,451" icon={<FileText />} sub="Canonical records" />
        <FederationStatCard label="Entities" value="1,087" icon={<Database />} sub="Resolved organizations" />
        <FederationStatCard label="Current state" value="Operational" tone="operational" sub="Semantic, not hard-coded" />
        <FederationStatCard label="Long-label stress case" value="$128,450,000" sub="Puerto Rico public-money contract obligations" />
      </section>

      <section className="atlas-grid" aria-label="Async state matrix">
        <StateCard state="loading" title="Loading">
          <QueryBoundary
            query={query({ data: undefined, dataUpdatedAt: 0, isLoading: true, isPending: true })}
            isEmpty={isEmpty}
          >
            <CachedRows />
          </QueryBoundary>
        </StateCard>
        <StateCard state="error" title="Error">
          <QueryBoundary
            query={query({ data: undefined, dataUpdatedAt: 0, error: new Error('fixture'), isError: true })}
            isEmpty={isEmpty}
          >
            <CachedRows />
          </QueryBoundary>
        </StateCard>
        <StateCard state="empty" title="Empty">
          <QueryBoundary query={query({ data: [] })} isEmpty={isEmpty} emptyLabel="No contracts">
            <CachedRows />
          </QueryBoundary>
        </StateCard>
        <StateCard state="filtered-empty" title="Filtered empty">
          <QueryBoundary
            query={query()}
            isEmpty={isEmpty}
            isFilteredEmpty
            filteredEmptyLabel="No contracts match these filters"
            onResetFilters={() => undefined}
          >
            <CachedRows />
          </QueryBoundary>
        </StateCard>
        <StateCard state="stale" title="Stale">
          <QueryBoundary
            query={query({ dataUpdatedAt: FIXTURE_UPDATED_AT - 10 * 60 * 1000, isStale: true })}
            isEmpty={isEmpty}
          >
            <CachedRows />
          </QueryBoundary>
        </StateCard>
        <StateCard state="offline" title="Offline">
          <QueryBoundary
            query={query({ data: undefined, dataUpdatedAt: 0, fetchStatus: 'paused', isLoading: true, isPending: true })}
            isEmpty={isEmpty}
          >
            <CachedRows />
          </QueryBoundary>
        </StateCard>
      </section>

      <div hidden data-runtime-probe="offline-cached">
        <QueryBoundary query={query({ fetchStatus: 'paused' })} isEmpty={isEmpty}>
          <CachedRows />
        </QueryBoundary>
      </div>
      <div hidden data-runtime-probe="offline-filtered">
        <QueryBoundary
          query={query({ fetchStatus: 'paused' })}
          isEmpty={isEmpty}
          isFilteredEmpty
          filteredEmptyLabel="No contracts match these filters"
          onResetFilters={() => undefined}
        >
          <CachedRows />
        </QueryBoundary>
      </div>
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Atlas />
  </React.StrictMode>,
)
