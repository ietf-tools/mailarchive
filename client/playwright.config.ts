import { defineConfig, devices } from '@playwright/test'

// Assumes the Nuxt dev server (:3000) and the Django backend (:8000) are
// already running with sample data + a built Elasticsearch index.
// Override the target with E2E_BASE_URL.
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
