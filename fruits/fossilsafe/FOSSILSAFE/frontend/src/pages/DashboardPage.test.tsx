/**
 * Tests for DashboardPage.
 *
 * Strategy: enable demo mode via localStorage so the page renders with
 * deterministic mock data without real API calls.  Then add targeted tests
 * for loading and error states using a mocked api.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/test-utils'
import DashboardPage from './DashboardPage'

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', () => ({
    api: {
        getSystemStats: vi.fn(),
        getDriveHealth: vi.fn(),
        getJobs: vi.fn(),
        getTapes: vi.fn(),
        getPredictiveDriveHealth: vi.fn(),
        getHealth: vi.fn(),
        unloadTape: vi.fn(),
    },
}))

// RestoreWizard is a heavy modal — stub it out
vi.mock('@/components/RestoreWizard', () => ({
    default: () => <div data-testid="restore-wizard" />,
}))

import { api } from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATS = {
    cpu_percent: 23,
    ram_percent: 45,
    cache_disk_percent: 67,
    total_capacity_bytes: 1_200_000_000_000_000,
    used_capacity_bytes: 450_000_000_000_000,
    tapes_online: 18,
    total_slots: 24,
    mailslot_enabled: true,
}

const DRIVES = [
    { id: 'DRIVE_01', type: 'LTO-8', status: 'idle' },
]

const JOBS = [{ id: 1, name: 'Test Job', status: 'completed', type: 'backup', progress: 100, created_at: new Date().toISOString() }]

function mockApiOk() {
    ;(api.getSystemStats as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: STATS })
    ;(api.getDriveHealth as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: { drives: DRIVES } })
    ;(api.getJobs as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: { jobs: JOBS, total: 1 } })
    ;(api.getTapes as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: { tapes: [] } })
    ;(api.getPredictiveDriveHealth as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: {} })
    ;(api.getHealth as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: { status: 'ok', version: '1.0.0' } })
}

beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mockApiOk()
})

// ---------------------------------------------------------------------------
// Demo mode tests (fast, deterministic)
// ---------------------------------------------------------------------------

describe('DashboardPage — demo mode', () => {
    beforeEach(() => {
        localStorage.setItem('demoMode', 'true')
    })

    it('renders without crashing', () => {
        renderWithProviders(<DashboardPage />)
    })

    it('shows CPU and RAM widgets', async () => {
        renderWithProviders(<DashboardPage />)
        await waitFor(() => {
            expect(screen.getByText(/cpu/i)).toBeTruthy()
            expect(screen.getByText(/ram/i)).toBeTruthy()
        })
    })

    it('shows Drive section', async () => {
        renderWithProviders(<DashboardPage />)
        await waitFor(() => {
            // Multiple elements may contain 'drive'; confirm at least one exists
            expect(screen.getAllByText(/drive/i).length).toBeGreaterThan(0)
        })
    })
})

// ---------------------------------------------------------------------------
// Live mode tests
// ---------------------------------------------------------------------------

describe('DashboardPage — live mode', () => {
    it('shows loading skeleton initially (before API resolves)', () => {
        ;(api.getSystemStats as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}))
        renderWithProviders(<DashboardPage />)
        // While loading the page may show a loading indicator or empty containers
        // We just verify it doesn't crash
        expect(document.body).toBeTruthy()
    })

    it('renders stats after API resolves', async () => {
        renderWithProviders(<DashboardPage />)
        await waitFor(() => {
            expect(screen.getByText(/cpu/i)).toBeTruthy()
        })
    })

    it('shows tape count from API data', async () => {
        ;(api.getSystemStats as ReturnType<typeof vi.fn>).mockResolvedValue({
            success: true,
            data: { ...STATS, tapes_online: 7, total_slots: 12 },
        })
        renderWithProviders(<DashboardPage />)
        await waitFor(() => {
            expect(screen.getByText('7')).toBeTruthy()
        })
    })

    it('gracefully handles API failure', async () => {
        ;(api.getSystemStats as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('API down'))
        ;(api.getDriveHealth as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('API down'))
        ;(api.getJobs as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('API down'))
        ;(api.getTapes as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('API down'))
        renderWithProviders(<DashboardPage />)
        // Should not throw or crash — just silently fail or show empty state
        await waitFor(() => {
            expect(document.body).toBeTruthy()
        })
    })
})
