import { describe, it, expect } from 'vitest'
import { ApiError } from '@/api/client'

// Smoke: confirms the toolchain (esbuild TS transform + @ alias + real-module
// import) works before the real suites rely on it.
describe('vitest toolchain smoke', () => {
  it('runs and resolves the @ alias to a real module', () => {
    const e = new ApiError('timeout', 'x')
    expect(e).toBeInstanceOf(Error)
    expect(e.kind).toBe('timeout')
  })
})
