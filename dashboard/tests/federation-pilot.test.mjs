import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { resolveFederationSemantic } from '@pr-federation/react/semantics'

const root = fileURLToPath(new URL('..', import.meta.url))
const source = async (path) => readFile(join(root, path), 'utf8')

test('semantic contracts resolve operational and async states', () => {
  assert.deepEqual(resolveFederationSemantic('operational', 'operational'), {
    kind: 'operational', value: 'operational', label: 'Operational', tone: 'success',
  })
  assert.equal(resolveFederationSemantic('asyncState', 'filtered_empty').value, 'filtered_empty')
  assert.equal(resolveFederationSemantic('asyncState', 'offline').tone, 'neutral')
  assert.equal(resolveFederationSemantic('asyncState', 'stale').tone, 'caution')
})

test('QueryBoundary uses every required shared async state', async () => {
  const text = await source('src/components/QueryBoundary.jsx')
  for (const component of [
    'FederationLoadingState', 'FederationErrorState', 'FederationEmptyState',
    'FederationFilteredEmptyState', 'FederationStaleDataState', 'FederationOfflineState',
    'FederationButton', 'FederationPanel',
  ]) assert.match(text, new RegExp(component))
})

test('QueryBoundary reacts to connectivity and stale deadlines', async () => {
  const text = await source('src/components/QueryBoundary.jsx')
  assert.match(text, /addEventListener\('online'/)
  assert.match(text, /addEventListener\('offline'/)
  assert.match(text, /setTimeout\(\(\) => setDeadlineTick/)

  const offlineBranch = text.indexOf('if (offline && empty)')
  const loadingBranch = text.indexOf('if (loading)')
  assert.ok(offlineBranch >= 0 && loadingBranch >= 0 && offlineBranch < loadingBranch)

  const filteredStart = text.indexOf('if (filteredEmpty)')
  const finalReturnStart = text.lastIndexOf('\n  return (')
  assert.ok(filteredStart >= 0 && finalReturnStart > filteredStart)
  assert.match(text.slice(filteredStart, finalReturnStart), /\{banner\}/)
})

test('filterable views delegate filtered-empty rendering to QueryBoundary', async () => {
  for (const path of [
    'src/components/ContractsTable.jsx',
    'src/components/EntitiesTable.jsx',
    'src/components/RelationshipGraph.jsx',
  ]) {
    const text = await source(path)
    assert.match(text, /isFilteredEmpty=/)
    assert.match(text, /onResetFilters=/)
    assert.doesNotMatch(text, />No (contracts|entities|relationships) match</)
  }
})

test('visual atlas exercises QueryBoundary runtime fixtures', async () => {
  const atlas = await source('src/visual-tests/FederationPilotAtlas.jsx')
  const runner = await source('scripts/run-federation-pilot-visual-checks.mjs')
  assert.match(atlas, /import QueryBoundary/)
  assert.match(atlas, /fetchStatus: 'paused', isLoading: true, isPending: true/)
  assert.match(runner, /initial offline state lost precedence/)
  assert.match(runner, /cached offline banner missing/)
  assert.match(runner, /filtered offline banner missing/)
})

test('visual evidence capture is animation-independent', async () => {
  const runner = await source('scripts/run-federation-pilot-visual-checks.mjs')
  assert.match(runner, /reducedMotion: 'reduce'/)
  assert.match(runner, /animations: 'disabled'/)
  assert.match(runner, /caret: 'hide'/)
  assert.match(runner, /schemaVersion: '1\.2\.0'/)
})

test('shared stat cards and operational badge replace local semantic colors', async () => {
  const text = await source('src/components/StatsBar.jsx')
  assert.match(text, /FederationStatCard/)
  assert.match(text, /FederationStatusBadge/)
  assert.match(text, /kind="operational"/)
  assert.doesNotMatch(text, /(bg-amber|bg-emerald|bg-destructive|text-destructive)/)
})

test('pilot component files contain no hard-coded semantic color utilities', async () => {
  const files = ['src/components/QueryBoundary.jsx', 'src/components/StatsBar.jsx']
  for (const path of files) {
    const text = await source(path)
    assert.doesNotMatch(text, /(amber|emerald|red-|yellow-|orange-|green-|text-destructive|bg-destructive)/)
  }
})
