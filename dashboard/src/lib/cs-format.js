// moneysweep-pr display helpers.

export function fmtMoney(v) {
  if (v == null) return '—'
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v)
  } catch {
    return String(v)
  }
}

// Badge/label palettes. A single lookup helper applies the shared slate fallback
// so every caller degrades the same way.
const SLATE_BADGE = 'bg-slate-500/15 text-slate-300 border-slate-500/30'
const tone = (map, key) => map[key] ?? SLATE_BADGE

const ENTITY_TONE = {
  agency: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  utility: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  firm: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  fund: 'bg-violet-500/15 text-violet-300 border-violet-500/30',
  person: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
}
export const entityTone = (t) => tone(ENTITY_TONE, t)

// Contract status maps onto the shared federation v0.2.0 status vocabulary.
// Colors now come from @pr-federation/react/styles.css via federationTone(role)
// → `.fd-status[data-status="<role>"]`, replacing the local hard-coded palette.
const STATUS_ROLE = {
  active: 'success',
  flagged: 'danger',
  amended: 'warning',
  executed: 'info',
}
export const statusRole = (s) => STATUS_ROLE[s] ?? 'neutral'

const EDGE_TONE = {
  LOCATED_IN: 'text-teal-300',
  AWARDED_TO: 'text-amber-300',
  CONTROLS: 'text-rose-300',
  AFFILIATED_WITH: 'text-violet-300',
  SUBSIDIARY_OF: 'text-sky-300',
}
export const edgeTone = (t) => EDGE_TONE[t] ?? 'text-slate-300'

// Tranche A caveat: award amounts are frequently unpopulated. Centralized here so
// StatsBar and MunicipalityAggregates agree on when to warn.
export const amountsUnpopulated = (stats) => (stats?.contractsWithAmount ?? 0) === 0
export const AMOUNTS_NOTE = 'award amounts not populated in Tranche A'
