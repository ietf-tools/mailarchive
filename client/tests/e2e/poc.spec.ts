import { test, expect } from '@playwright/test'

// Requires the Nuxt dev server (:3000) + Django backend (:8000) running with
// the sample data loaded and the Elasticsearch index built.

test('home renders the search box', async ({ page }) => {
  await page.goto('/arch/')
  await expect(page.getByPlaceholder('Search the mail archive…')).toBeVisible()
})

test('browse page lists email lists', async ({ page }) => {
  await page.goto('/arch/browse/')
  await expect(page.getByRole('heading', { name: 'Browse lists' })).toBeVisible()
})

test('search by list shows a result count', async ({ page }) => {
  await page.goto('/arch/search/?email_list=pubone')
  await expect(page.getByText(/results/)).toBeVisible()
})

test('clicking a result opens the preview pane', async ({ page }) => {
  await page.goto('/arch/search/?email_list=pubone')
  const firstRow = page.locator('tbody tr').first()
  await firstRow.click()
  await expect(page.getByText('Open full message →')).toBeVisible()
})
