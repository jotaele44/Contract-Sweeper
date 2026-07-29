
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const expectedUrl = 'https://github.com/jotaele44/thehub-pr/releases/download/federation-design-v0.4.1/pr-federation-react-0.4.1.tgz'
const expectedSha256 = 'a609b6e88103e6bdfc4af8305e8997843f6e2c1e60ae386ef17ae3f211272f45'

const readJson = async (path) => JSON.parse(await readFile(path, 'utf8'))
const pkg = await readJson(join(root, 'package.json'))
const lock = await readJson(join(root, 'package-lock.json'))
const installed = await readJson(join(root, 'node_modules/@pr-federation/react/package.json'))
const manifest = await readJson(join(root, 'node_modules/@pr-federation/react/dist/release-manifest.json'))
const snapshot = await readJson(join(root, 'node_modules/@pr-federation/react/api-snapshot.json'))
const tokens = await readJson(join(root, 'node_modules/@pr-federation/react/dist/federation.tokens.json'))
const harness = await readJson(join(root, 'node_modules/@pr-federation/react/dist/test-harness.contract.json'))

assert.equal(pkg.dependencies['@pr-federation/react'], expectedUrl)
assert.equal(lock.packages['node_modules/@pr-federation/react'].resolved, expectedUrl)
assert.equal(installed.version, '0.4.1')
assert.equal(manifest.package, '@pr-federation/react')
assert.equal(manifest.version, '0.4.1')
assert.equal(manifest.expectedTag, 'federation-design-v0.4.1')
assert.equal(manifest.tokenVersion, '2.0.0')
assert.equal(tokens.version, '2.0.0')
assert.equal(manifest.mutableReferencesAllowed, false)
assert.equal(Object.keys(manifest.sourceSha256).length, 11)
assert.equal(snapshot.exports.length, 35)
assert.equal(snapshot.removedExports.length, 0)
assert.equal(harness.viewports.length, 6)
assert.equal(harness.requirements.axeCriticalSerious, 0)
assert.equal(harness.requirements.horizontalOverflow, false)

const response = await fetch(expectedUrl, { redirect: 'follow' })
assert.equal(response.ok, true, `release download failed: ${response.status}`)
const bytes = Buffer.from(await response.arrayBuffer())
const actualSha256 = createHash('sha256').update(bytes).digest('hex')
assert.equal(actualSha256, expectedSha256)

console.log(JSON.stringify({
  package: installed.name,
  version: installed.version,
  release: manifest.expectedTag,
  tarballSha256: actualSha256,
  sourceHashes: Object.keys(manifest.sourceSha256).length,
  apiExports: snapshot.exports.length,
  tokenVersion: tokens.version,
  mutableReferencesAllowed: manifest.mutableReferencesAllowed,
  viewports: harness.viewports.length,
}, null, 2))
