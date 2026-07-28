import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const dashboard = fileURLToPath(new URL('..', import.meta.url))
const repo = resolve(dashboard, '..')
const outputDir = process.env.PILOT_SCREENSHOT_DIR || join(repo, 'docs/evidence/moneysweep-federation-design-pilot-v0-1')
const reportPath = process.env.PILOT_REPORT_PATH || join(outputDir, 'visual-check-report.json')
const baseUrl = 'http://127.0.0.1:4173/federation-pilot-atlas.html'
const viewports = [
  { name: 'mobile-compact', width: 390, height: 844 },
  { name: 'mobile-wide', width: 430, height: 932 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'desktop-wide', width: 1440, height: 900 },
  { name: 'wide', width: 1920, height: 1080 },
]
const stateExpectations = {
  loading: 'Loading records',
  error: 'Couldn’t reach the backend',
  empty: 'No contracts',
  'filtered-empty': 'No contracts match these filters',
  stale: 'This view may be stale',
  offline: 'MoneySweep is offline',
}

await mkdir(outputDir, { recursive: true })
const server = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '4173'], {
  cwd: dashboard,
  stdio: ['ignore', 'pipe', 'pipe'],
})
let serverLog = ''
server.stdout.on('data', (chunk) => { serverLog += chunk })
server.stderr.on('data', (chunk) => { serverLog += chunk })

async function waitForServer() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(baseUrl)
      if (response.ok) return
    } catch { /* server is still starting */ }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 500))
  }
  throw new Error(`Vite did not start.\n${serverLog}`)
}

async function verifyRuntimeStates(page, viewport, theme) {
  for (const [state, expectedText] of Object.entries(stateExpectations)) {
    const card = page.locator(`[data-state-card="${state}"]`)
    assert.equal(await card.count(), 1, `${viewport.name}/${theme} missing ${state} state card`)
    assert.ok(
      (await card.textContent()).includes(expectedText),
      `${viewport.name}/${theme} ${state} card did not render ${expectedText}`,
    )
  }

  const initialOffline = await page.locator('[data-state-card="offline"]').textContent()
  assert.equal(initialOffline.includes('Loading records'), false, `${viewport.name}/${theme} initial offline state lost precedence`)

  const cachedOffline = await page.locator('[data-runtime-probe="offline-cached"]').textContent()
  assert.ok(cachedOffline.includes('Offline — showing cached data'), `${viewport.name}/${theme} cached offline banner missing`)
  assert.ok(cachedOffline.includes('Cached contract rows remain visible.'), `${viewport.name}/${theme} cached offline data hidden`)

  const filteredOffline = await page.locator('[data-runtime-probe="offline-filtered"]').textContent()
  assert.ok(filteredOffline.includes('Offline — showing cached data'), `${viewport.name}/${theme} filtered offline banner missing`)
  assert.ok(filteredOffline.includes('No contracts match these filters'), `${viewport.name}/${theme} filtered-empty state missing offline`)
}

const browser = await chromium.launch()
const results = []
try {
  await waitForServer()
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      reducedMotion: 'reduce',
    })
    const page = await context.newPage()
    const perTheme = []

    for (const theme of ['dark', 'light']) {
      await page.goto(`${baseUrl}?theme=${theme}`, { waitUntil: 'networkidle' })
      await verifyRuntimeStates(page, viewport, theme)

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
      assert.equal(overflow, false, `${viewport.name}/${theme} has horizontal overflow`)

      const analysis = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze()
      const blocking = analysis.violations.filter((item) => item.impact === 'critical' || item.impact === 'serious')
      assert.deepEqual(blocking, [], `${viewport.name}/${theme} axe violations: ${JSON.stringify(blocking)}`)

      if (theme === 'dark') {
        let focusedButton = false
        for (let attempt = 0; attempt < 20; attempt += 1) {
          await page.keyboard.press('Tab')
          focusedButton = await page.evaluate(() => document.activeElement?.tagName === 'BUTTON')
          if (focusedButton) break
        }
        assert.equal(focusedButton, true, `${viewport.name} keyboard traversal did not reach a button`)

        const targetViolations = await page.locator('button:visible').evaluateAll((buttons) => buttons
          .map((button) => {
            const rect = button.getBoundingClientRect()
            return { text: button.textContent?.trim(), width: rect.width, height: rect.height }
          })
          .filter((item) => item.width < 44 || item.height < 44))
        assert.deepEqual(targetViolations, [], `${viewport.name} touch targets below 44px: ${JSON.stringify(targetViolations)}`)

        const screenshot = join(outputDir, `${viewport.name}.png`)
        await page.screenshot({
          path: screenshot,
          fullPage: true,
          animations: 'disabled',
          caret: 'hide',
        })
        const digest = createHash('sha256').update(await readFile(screenshot)).digest('hex')
        results.push({ ...viewport, screenshot: `${viewport.name}.png`, sha256: digest })
      }
      perTheme.push({ theme, criticalSeriousViolations: blocking.length, horizontalOverflow: overflow })
    }
    results.at(-1).themes = perTheme
    await context.close()
  }
} finally {
  await browser.close()
  server.kill('SIGTERM')
}

const report = {
  schemaVersion: '1.2.0',
  viewports: results,
  requirements: {
    axeCriticalSerious: 0,
    horizontalOverflow: false,
    minimumTouchTargetCssPx: 44,
    keyboardButtonReachable: true,
    queryBoundaryRuntimeStates: Object.keys(stateExpectations),
    initialOfflinePrecedesLoading: true,
    cachedOfflineDataVisible: true,
    filteredEmptyPreservesStatusBanner: true,
    deterministicCapture: {
      reducedMotion: 'reduce',
      animations: 'disabled',
      caret: 'hide',
    },
    themes: ['dark', 'light'],
  },
}
await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`)
console.log(JSON.stringify(report, null, 2))
process.exit(process.exitCode || 0)
