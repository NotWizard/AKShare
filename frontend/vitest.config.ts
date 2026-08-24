import { defineConfig } from 'vitest/config'
import { fileURLToPath, URL } from 'node:url'

// Vitest config — mirrors vite.config.ts's `@` alias so tests import modules the
// same way the app does. Node environment on purpose: the logic under test
// (client retry/dedupe/cache, SSE parsing, stores, composables) is exercised
// with a mocked `fetch` and stubbed rAF, so no jsdom/happy-dom dependency is
// pulled in.
export default defineConfig({
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.spec.ts'],
    clearMocks: true,
  },
})
