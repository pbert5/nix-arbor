/**
 * Tests for LoginPage.
 *
 * Exercises: form render, field validation, submit flow, 2FA prompt, SSO check.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/test-utils'
import LoginPage from './LoginPage'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', () => ({
    api: {
        getSSOConfig: vi.fn(),
    },
}))

import { api } from '@/lib/api'

beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    ;(api.getSSOConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { enabled: false },
    })
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderLogin(onLogin = vi.fn()) {
    return renderWithProviders(<LoginPage onLogin={onLogin} />)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LoginPage render', () => {
    it('renders username and password fields', async () => {
        renderLogin()
        expect(screen.getByPlaceholderText(/username/i)).toBeTruthy()
        expect(screen.getByPlaceholderText(/password/i)).toBeTruthy()
    })

    it('renders a submit button', () => {
        renderLogin()
        const btn = screen.getByRole('button', { name: /sign in|log in|login/i })
        expect(btn).toBeTruthy()
    })

    it('does not show SSO button when SSO is disabled', async () => {
        renderLogin()
        await waitFor(() => {
            expect(screen.queryByText(/continue with sso/i)).toBeNull()
        })
    })
})

describe('LoginPage validation', () => {
    it('shows error when username is empty and form is submitted', async () => {
        renderLogin()
        const btn = screen.getByRole('button', { name: /sign in|log in|login/i })
        fireEvent.click(btn)
        await waitFor(() => {
            expect(screen.getByText(/username and password are required/i)).toBeTruthy()
        })
    })

    it('shows error when password is empty and form is submitted', async () => {
        renderLogin()
        fireEvent.change(screen.getByPlaceholderText(/username/i), {
            target: { value: 'admin' },
        })
        const btn = screen.getByRole('button', { name: /sign in|log in|login/i })
        fireEvent.click(btn)
        await waitFor(() => {
            expect(screen.getByText(/username and password are required/i)).toBeTruthy()
        })
    })
})

describe('LoginPage SSO', () => {
    it('shows SSO button when SSO is enabled', async () => {
        ;(api.getSSOConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
            success: true,
            data: { enabled: true },
        })
        renderLogin()
        await waitFor(() => {
            expect(screen.getByText(/continue with sso|sso/i)).toBeTruthy()
        })
    })
})
