import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (!('ResizeObserver' in globalThis)) {
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverMock
}

// Mock fetch globally
globalThis.fetch = vi.fn() as any
