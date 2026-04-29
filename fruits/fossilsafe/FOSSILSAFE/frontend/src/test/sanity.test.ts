import { describe, it, expect } from 'vitest'

/**
 * Sanity suite — trivial checks that the test environment is wired up correctly.
 * Real coverage lives in the per-feature test files.
 */
describe('test environment sanity', () => {
    it('evaluates boolean expressions', () => {
        expect(true).toBe(true)
        expect(false).not.toBe(true)
    })

    it('has access to jsdom globals', () => {
        expect(typeof window).toBe('object')
        expect(typeof document).toBe('object')
    })

    it('has a localStorage stub', () => {
        localStorage.setItem('__sanity__', '42')
        expect(localStorage.getItem('__sanity__')).toBe('42')
        localStorage.removeItem('__sanity__')
    })
})

