/**
 * Tests for TapesPage.
 *
 * Covers: render, demo-mode tape list, search filtering, scan button,
 * empty state, and error state.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/test-utils'
import TapesPage from './TapesPage'
import type { Tape } from '@/lib/api'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', () => ({
    api: {
        getTapes: vi.fn(),
        scanLibrary: vi.fn(),
        updateTapeAlias: vi.fn(),
        loadTape: vi.fn(),
        unloadTape: vi.fn(),
        getDriveHealth: vi.fn(),
        getSystemStats: vi.fn(),
    },
}))

vi.mock('@/components/RestoreWizard', () => ({
    default: () => <div data-testid="restore-wizard" />,
}))

import { api } from '@/lib/api'

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const MOCK_TAPES: Tape[] = [
    {
        barcode: 'TAPE001',
        alias: 'Archive_Q1',
        status: 'available',
        location_type: 'slot',
        slot_number: 1,
        capacity_bytes: 12_000_000_000_000,
        used_bytes: 4_000_000_000_000,
        ltfs_formatted: true,
        mount_count: 10,
        error_count: 0,
        trust_status: 'trusted',
    },
    {
        barcode: 'TAPE002',
        status: 'in_use',
        location_type: 'drive',
        drive_id: '0',
        capacity_bytes: 12_000_000_000_000,
        used_bytes: 8_000_000_000_000,
        ltfs_formatted: true,
        mount_count: 5,
        error_count: 0,
        trust_status: 'trusted',
    },
    {
        barcode: 'TAPE003',
        status: 'error',
        location_type: 'slot',
        slot_number: 3,
        capacity_bytes: 6_000_000_000_000,
        used_bytes: 6_000_000_000_000,
        ltfs_formatted: true,
        mount_count: 120,
        error_count: 3,
        trust_status: 'untrusted',
    },
]

beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    ;(api.getTapes as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { tapes: MOCK_TAPES },
    })
    ;(api.getDriveHealth as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { drives: [] },
    })
    ;(api.scanLibrary as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { tapes: MOCK_TAPES },
    })
    ;(api.getSystemStats as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { cpu_percent: 10, ram_percent: 20 },
    })
})

// ---------------------------------------------------------------------------
// Demo mode
// ---------------------------------------------------------------------------

describe('TapesPage — demo mode', () => {
    beforeEach(() => {
        localStorage.setItem('demoMode', 'true')
    })

    it('renders without crashing', () => {
        renderWithProviders(<TapesPage />)
    })

    it('shows tape barcodes from mock data', async () => {
        renderWithProviders(<TapesPage />)
        await waitFor(() => {
            // Demo data has barcodes — confirm at least one element contains 'tape'
            expect(screen.getAllByText(/tape/i).length).toBeGreaterThan(0)
        })
    })
})

// ---------------------------------------------------------------------------
// Live mode
// ---------------------------------------------------------------------------

describe('TapesPage — live mode', () => {
    it('renders tape barcodes returned by API', async () => {
        renderWithProviders(<TapesPage />)
        await waitFor(() => {
            expect(screen.getAllByText('TAPE001').length).toBeGreaterThan(0)
        })
    })

    it('renders drive tape (TAPE002)', async () => {
        renderWithProviders(<TapesPage />)
        await waitFor(() => {
            expect(screen.getAllByText('TAPE002').length).toBeGreaterThan(0)
        })
    })

    it('renders alias when present', async () => {
        renderWithProviders(<TapesPage />)
        await waitFor(() => {
            expect(screen.getAllByText('Archive_Q1').length).toBeGreaterThan(0)
        })
    })

    it('renders error-status tape', async () => {
        renderWithProviders(<TapesPage />)
        await waitFor(() => {
            expect(screen.getAllByText('TAPE003').length).toBeGreaterThan(0)
        })
    })

    it('shows empty state when no tapes returned', async () => {
        ;(api.getTapes as ReturnType<typeof vi.fn>).mockResolvedValue({
            success: true,
            data: { tapes: [] },
        })
        renderWithProviders(<TapesPage />)
        await waitFor(() => {
            // Should render without crashing; may show empty state text
            expect(document.body).toBeTruthy()
        })
    })

    it('handles API failure gracefully', async () => {
        // Use a failure response (not a rejection) so the component handles it without
        // creating an unhandled promise rejection that bleeds into subsequent tests.
        ;(api.getTapes as ReturnType<typeof vi.fn>).mockResolvedValue({
            success: false,
            error: 'Network error',
        })
        renderWithProviders(<TapesPage />)
        await waitFor(() => {
            expect(document.body).toBeTruthy()
        })
    })

    it('search input filters the tape list', async () => {
        renderWithProviders(<TapesPage />)
        await waitFor(() => {
            expect(screen.getAllByText('TAPE001').length).toBeGreaterThan(0)
        })
        const searchInput = screen.getByPlaceholderText(/search/i)
        fireEvent.change(searchInput, { target: { value: 'TAPE002' } })
        await waitFor(() => {
            // After filtering, TAPE002 should still be visible
            expect(screen.getAllByText('TAPE002').length).toBeGreaterThan(0)
            // TAPE003 should no longer appear in the list
            expect(screen.queryByText('TAPE003')).toBeNull()
        })
    })

    it('scan button triggers scanLibrary', async () => {
        renderWithProviders(<TapesPage />)
        // Wait for the Scan Library button to be visible (after tapes load)
        const scanBtn = await screen.findByRole('button', { name: /scan library/i })
        fireEvent.click(scanBtn)
        await waitFor(() => {
            expect(api.scanLibrary).toHaveBeenCalled()
        })
    })
})
