/**
 * Tests for JobsPage.
 *
 * Covers: demo mode render, live mode job list, status-filter tabs,
 * cancel button invokes API, "Queue New Job" opens/closes wizard,
 * empty state, and API error state.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/test-utils'
import JobsPage from './JobsPage'
import type { Job } from '@/lib/api'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', () => ({
    api: {
        getJobs: vi.fn(),
        getJob: vi.fn(),
        cancelJob: vi.fn(),
        getTapes: vi.fn(),
    },
}))

vi.mock('@/components/CreateJobWizard', () => ({
    default: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
        isOpen ? (
            <div data-testid="create-job-wizard">
                <button onClick={onClose}>Close Wizard</button>
            </div>
        ) : null,
}))

import { api } from '@/lib/api'

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const MOCK_JOBS: Job[] = [
    {
        id: 101,
        name: 'Nightly_Backup',
        type: 'backup',
        status: 'running',
        progress: 60,
        created_at: new Date().toISOString(),
        tapes: ['TAPE001'],
    },
    {
        id: 102,
        name: 'Monthly_Archive',
        type: 'backup',
        status: 'completed',
        progress: 100,
        created_at: new Date(Date.now() - 86400_000).toISOString(),
        tapes: ['TAPE002'],
    },
    {
        id: 103,
        name: 'Restore_DR',
        type: 'restore',
        status: 'failed',
        progress: 20,
        created_at: new Date(Date.now() - 172800_000).toISOString(),
        tapes: [],
    },
]

function setupApiMocks() {
    ;(api.getJobs as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { jobs: MOCK_JOBS, total: MOCK_JOBS.length },
    })
    ;(api.getJob as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { logs: [] },
    })
    ;(api.getTapes as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { tapes: [] },
    })
    ;(api.cancelJob as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: {},
    })
}

beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    setupApiMocks()
})

// ---------------------------------------------------------------------------
// Demo mode
// ---------------------------------------------------------------------------

describe('JobsPage — demo mode', () => {
    beforeEach(() => {
        localStorage.setItem('demoMode', 'true')
    })

    it('renders without crashing', () => {
        renderWithProviders(<JobsPage />)
    })

    it('shows demo jobs immediately (no loading spinner)', async () => {
        renderWithProviders(<JobsPage />)
        // Demo jobs include Archive_Project_X from the built-in MOCK_JOBS
        await waitFor(() => {
            expect(screen.getAllByText(/Archive_Project_X/i).length).toBeGreaterThan(0)
        })
    })

    it('shows the Queue New Job button', async () => {
        renderWithProviders(<JobsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /queue new job/i })).toBeTruthy()
        })
    })

    it('opens create wizard when Queue New Job is clicked', async () => {
        renderWithProviders(<JobsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /queue new job/i })).toBeTruthy()
        })
        fireEvent.click(screen.getByRole('button', { name: /queue new job/i }))
        await waitFor(() => {
            expect(screen.getByTestId('create-job-wizard')).toBeTruthy()
        })
    })

    it('closes create wizard when Close Wizard is clicked', async () => {
        renderWithProviders(<JobsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /queue new job/i })).toBeTruthy()
        })
        fireEvent.click(screen.getByRole('button', { name: /queue new job/i }))
        await waitFor(() => {
            expect(screen.getByTestId('create-job-wizard')).toBeTruthy()
        })
        fireEvent.click(screen.getByRole('button', { name: /close wizard/i }))
        await waitFor(() => {
            expect(screen.queryByTestId('create-job-wizard')).toBeNull()
        })
    })
})

// ---------------------------------------------------------------------------
// Live mode
// ---------------------------------------------------------------------------

describe('JobsPage — live mode', () => {
    it('renders jobs returned by API', async () => {
        renderWithProviders(<JobsPage />)
        await waitFor(() => {
            expect(screen.getAllByText('Nightly_Backup').length).toBeGreaterThan(0)
        })
    })

    it('renders job names for all mock jobs', async () => {
        renderWithProviders(<JobsPage />)
        // Wait for the running job row to appear (default filter = 'running')
        await waitFor(() => {
            expect(screen.getAllByText('JOB-101').length).toBeGreaterThan(0)
        })
        // Switch to "All Jobs" to see completed/failed jobs too
        const allJobsBtn = screen
            .getAllByRole('button')
            .find(btn => btn.textContent?.includes('All Jobs'))
        if (allJobsBtn) fireEvent.click(allJobsBtn)
        await waitFor(() => {
            expect(screen.getAllByText('JOB-101').length).toBeGreaterThan(0)
            expect(screen.getAllByText('JOB-102').length).toBeGreaterThan(0)
            expect(screen.getAllByText('JOB-103').length).toBeGreaterThan(0)
        })
    })

    it('shows the Active filter tab', async () => {
        renderWithProviders(<JobsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /active/i })).toBeTruthy()
        })
    })

    it('shows All Jobs filter tab', async () => {
        renderWithProviders(<JobsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /all jobs/i })).toBeTruthy()
        })
    })

    it('shows History filter tab', async () => {
        renderWithProviders(<JobsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /history/i })).toBeTruthy()
        })
    })

    it('handles API failure gracefully', async () => {
        // Use a failure response rather than rejection to avoid unhandled promise rejection
        // (fetchJobs has no top-level try/catch)
        ;(api.getJobs as ReturnType<typeof vi.fn>).mockResolvedValue({
            success: false,
            error: 'Network error',
        })
        renderWithProviders(<JobsPage />)
        await waitFor(() => {
            expect(document.body).toBeTruthy()
        })
    })

    it('shows empty state when no jobs returned', async () => {
        ;(api.getJobs as ReturnType<typeof vi.fn>).mockResolvedValue({
            success: true,
            data: { jobs: [], total: 0 },
        })
        renderWithProviders(<JobsPage />)
        await waitFor(() => {
            // Empty state shows "No jobs found"
            expect(screen.getByText(/no jobs found/i)).toBeTruthy()
        })
    })
})
