
import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource-variable/inter'
import '@fontsource/jetbrains-mono'
import '@/index.css'
import '@pr-federation/react/styles.css'
import '@/styles/federation.css'
import '@/styles/pilot.css'
import '@/styles/federation-pilot-atlas.css'
import {
  FederationButton,
  FederationEmptyState,
  FederationErrorState,
  FederationFilteredEmptyState,
  FederationLoadingState,
  FederationOfflineState,
  FederationPanel,
  FederationStaleDataState,
  FederationStatCard,
  FederationStatusBadge,
} from '@pr-federation/react'
import { AlertTriangle, Clock3, Database, FileText, Inbox, SearchX, WifiOff } from 'lucide-react'

const params = new URLSearchParams(window.location.search)
document.documentElement.dataset.repo = 'moneysweep-pr'
document.documentElement.dataset.theme = params.get('theme') === 'light' ? 'light' : 'dark'

const retry = <FederationButton variant="secondary">Retry</FederationButton>
const clear = <FederationButton variant="secondary">Clear filters</FederationButton>

function StateCard({ title, children }) {
  return (
    <FederationPanel className="atlas-card">
      <h2>{title}</h2>
      {children}
    </FederationPanel>
  )
}

function Atlas() {
  return (
    <main className="atlas-shell">
      <header className="atlas-header">
        <div>
          <p className="atlas-kicker">MoneySweep pilot · immutable RC</p>
          <h1>Federation async-state and primitive atlas</h1>
          <p>Shared loading, error, empty, filtered-empty, stale, offline, button, panel, stat-card and semantic-badge contracts.</p>
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
        <StateCard title="Loading">
          <FederationLoadingState title="Loading contracts" description="Retrieving the latest records." />
        </StateCard>
        <StateCard title="Error">
          <FederationErrorState icon={<AlertTriangle />} title="Couldn’t reach the backend" description="Retry when the service is available." action={retry} />
        </StateCard>
        <StateCard title="Empty">
          <FederationEmptyState icon={<Inbox />} title="No contracts" description="No canonical records are available yet." />
        </StateCard>
        <StateCard title="Filtered empty">
          <FederationFilteredEmptyState icon={<SearchX />} title="No contracts match these filters" description="Adjust or clear the active filters." action={clear} />
        </StateCard>
        <StateCard title="Stale">
          <FederationStaleDataState icon={<Clock3 />} title="This view may be stale" description="Refresh to check for newer records." action={retry} />
        </StateCard>
        <StateCard title="Offline">
          <FederationOfflineState icon={<WifiOff />} title="MoneySweep is offline" description="Cached records remain available." action={retry} />
        </StateCard>
      </section>
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Atlas />
  </React.StrictMode>,
)
