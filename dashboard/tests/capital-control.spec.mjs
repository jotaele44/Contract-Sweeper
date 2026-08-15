import { expect, test } from '@playwright/test'

test('capital and control graph is reachable from the dashboard', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.getByRole('tab', { name: 'Capital' }).click()
  await expect(page.getByTestId('capital-control-panel')).toBeVisible()
  await expect(page.getByText('Legal holder, investor family, and ultimate parent are intentionally separate identity levels.')).toBeVisible()
})
