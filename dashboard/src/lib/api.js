// REST client for the moneysweep-pr FastAPI backend.
// Backend: server/backend/main.py  (uvicorn server.backend.main:app --port 8000)
// Reads the frozen canonical_v1 CSVs. award amounts are frequently null.
import snapshot from './snapshot.json' // {} in normal builds; populated for VITE_OFFLINE exports
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

// Offline export build: resolve from an embedded data snapshot instead of fetching.
// (A file:// page cannot fetch at all, so standalone exports bake the data in.)
const OFFLINE = import.meta.env.VITE_OFFLINE === '1'

// Fetch JSON, THROWING on any failure so react-query surfaces isError/retry.
// Offline builds resolve from the embedded snapshot instead of the network.
async function fetchJSON(path, offlineFallback = null) {
  if (OFFLINE) {
    const key = path.split('?')[0] // server-side filters degrade to the unfiltered snapshot
    return key in snapshot ? snapshot[key] : offlineFallback
  }
  const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(8000) })
  if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`)
  return res.json()
}

const qs = (params) => {
  const p = Object.entries(params).filter(([, v]) => v != null && v !== '')
  return p.length ? '?' + new URLSearchParams(p).toString() : ''
}

// Health is polled and drives the up/down indicator, so it stays soft: a failed
// probe means "down", not a thrown query.
export const getHealth = async () => {
  try {
    return await fetchJSON('/health', { status: 'down', rows: {} })
  } catch {
    return { status: 'down', rows: {} }
  }
}
export const getContracts = (f = {}) => fetchJSON(`/contracts${qs(f)}`, [])
export const getEntities = (f = {}) => fetchJSON(`/entities${qs(f)}`, [])
export const getEdges = (f = {}) => fetchJSON(`/edges${qs(f)}`, [])
export const getMunicipalities = () => fetchJSON('/municipalities', [])
export const getStats = () => fetchJSON('/stats', null)
