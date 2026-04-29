/**
 * Tests for App state machine: loading → setup | login | authenticated.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/test-utils'
import { api } from '@/lib/api'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', () => ({
    api: {
        getSetupStatus: vi.fn(),
        getSSOConfig: vi.fn(),
        getSystemStats: vi.fn(),
        getDriveHealth: vi.fn(),
        getJobs: vi.fn(),
        getTapes: vi.fn(),
        getPredictiveDriveHealth: vi.fn(),
        getHealth: vi.fn(),
        getMailSlotConfig: vi.fn(),
        getMe: vi.fn(),
    },
}))

// App imports AppLayout which may import more things; mock heavy child pages
vi.mock('@/pages/DashboardPage', () => ({
    default: () => <div data-testid="dashboard-page">Dashboard</div>,
}))
vi.mock('@/pages/SetupWizard', () => ({
    default: ({ onComplete }: { onComplete: (t: string, u: string, r: string) => void }) => (
        <div data-testid="setup-wizard">
            <button onClick={() => onComplete('tok', 'admin', 'admin')}>Complete Setup</button>
        </div>
    ),
}))
vi.mock('@/pages/LoginPage', () => ({
    default: ({ onLogin }: { onLogin: (t: string, u: string, r: string) => void }) => (
        <div data-testid="login-page">
            <button onClick={() => onLogin('tok', 'admin', 'admin')}>Log in</button>
        </div>
    ),
}))
vi.mock('@/layouts/AppLayout', () => ({
    default: () => <div data-testid="app-layout">App Layout</div>,
}))

// ---------------------------------------------------------------------------
// Import App after mocks are set up
// ---------------------------------------------------------------------------

// We import lazily inside tests to ensure mocks apply

beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    ;(api.getSSOConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { enabled: false, issuer: '' },
    })
})

describe('App state machine', () => {
    it('shows loading state while checking setup status', async () => {
        // Never resolves
        ;(api.getSetupStatus as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}))
        const { default: App } = await import('./App')
        renderWithProviders(<App />)
        expect(screen.getByText(/initializing/i)).toBeTruthy()
    })

    it('shows setup wizard when setup is required', async () => {
        ;(api.getSetupStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
            success: true,
            data: { setup_required: true },
        })
        const { default: App } = await import('./App')
        renderWithProviders(<App />)
        await waitFor(() => {
            expect(screen.getByTestId('setup-wizard')).toBeTruthy()
        })
    })

    it('shows login page when setup is complete and not authenticated', async () => {
        ;(api.getSetupStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
            success: true,
            data: { setup_required: false },
        })
        const { default: App } = await import('./App')
        renderWithProviders(<App />)
        await waitFor(() => {
            expect(screen.getByTestId('login-page')).toBeTruthy()
        })
    })

    it('shows error panel when backend is unreachable after retries', async () => {
        ;(api.getSetupStatus as ReturnType<typeof vi.fn>).mockRejectedValue(
            new Error('Connection refused'),
        )
        const { default: App } = await import('./App')
        renderWithProviders(<App />)
        await waitFor(
            () => {
                expect(screen.getByText(/could not finish startup/i)).toBeTruthy()
            },
            { timeout: 15000 },
        )
    }, 20000)
})
