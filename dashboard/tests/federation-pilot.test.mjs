
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
