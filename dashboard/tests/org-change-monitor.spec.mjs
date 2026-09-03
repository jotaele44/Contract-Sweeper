import { expect, test } from '@playwright/test'

test('organization change monitor is reachable from the dashboard', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.getByRole('tab', { name: 'Gov Changes' }).click()
  await expect(page.getByTestId('government-change-monitor')).toBeVisible()
})
