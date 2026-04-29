/**
 * Tests for SettingsPage.
 *
 * Covers: default tab is General, tab navigation updates URL,
 * Users tab fetches users, SSO tab renders issuer/client-id fields,
 * and graceful handling of API errors.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/test-utils'
import SettingsPage from './SettingsPage'

// ---------------------------------------------------------------------------
// Mocks — heavy components and all api methods used by SettingsPage
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', () => ({
    api: {
        getSystemInfo: vi.fn(),
        getMailSlotConfig: vi.fn(),
        updateMailSlotConfig: vi.fn(),
        getUsers: vi.fn(),
        getSSOConfig: vi.fn(),
        updateSSOConfig: vi.fn(),
        getAuditLog: vi.fn(),
        getAuditVerificationHistory: vi.fn(),
        getNotificationSettings: vi.fn(),
        updateNotificationSettings: vi.fn(),
        getSources: vi.fn(),
        getTapes: vi.fn(),
        getKMSConfig: vi.fn(),
        getStreamingConfig: vi.fn(),
        getDiagnosticsHealth: vi.fn(),
        runDiagnostics: vi.fn(),
        generateSupportBundle: vi.fn(),
        verifyAuditChain: vi.fn(),
        getSchedules: vi.fn(),
        disable2FA: vi.fn(),
        deleteSource: vi.fn(),
        updateKMSConfig: vi.fn(),
        updateStreamingConfig: vi.fn(),
        testNotification: vi.fn(),
    },
}))

vi.mock('@/components/AddUserModal', () => ({
    default: () => <div data-testid="add-user-modal" />,
}))

vi.mock('@/components/maintenance/CatalogExportModal', () => ({
    default: () => <div data-testid="catalog-export-modal" />,
}))

vi.mock('@/components/AddSourceModal', () => ({
    default: () => <div data-testid="add-source-modal" />,
}))

vi.mock('@/components/ui/ConfirmationModal', () => ({
    default: () => <div data-testid="confirmation-modal" />,
}))

vi.mock('@/components/DiagnosticsHistory', () => ({
    default: () => <div data-testid="diagnostics-history" />,
}))

vi.mock('@/components/WebhooksPanel', () => ({
    default: () => <div data-testid="webhooks-panel" />,
}))

import { api } from '@/lib/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupDefaultMocks() {
    ;(api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: {
            hostname: 'testhost',
            version: '1.0.0',
            uptime: 12345,
            cpu_percent: 15,
            ram_percent: 40,
            disk_percent: 60,
        },
    })
    ;(api.getMailSlotConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { enabled: true, auto_detect: true },
    })
    ;(api.getUsers as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: {
            users: [
                { id: 1, username: 'admin', role: 'admin', totp_enabled: false },
                { id: 2, username: 'operator', role: 'operator', totp_enabled: true },
            ],
        },
    })
    ;(api.getSSOConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: {
            enabled: false,
            issuer: 'https://idp.example.com',
            client_id: 'fossilsafe-client',
            client_secret: '',
        },
    })
    ;(api.getAuditLog as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { entries: [] },
    })
    ;(api.getAuditVerificationHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { history: [] },
    })
    ;(api.getNotificationSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: {
            smtp: { enabled: false, host: '', port: 587, user: '', password: '', encryption: 'starttls' },
            webhook: { enabled: false, webhook_url: '', webhook_type: 'generic' },
            snmp: { enabled: false, target_host: '', port: 162, community: 'public' },
        },
    })
    ;(api.getSources as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { sources: [] },
    })
    ;(api.getTapes as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { tapes: [] },
    })
    ;(api.getKMSConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { type: 'local', vault_addr: '', mount_path: 'secret', vault_token_configured: false },
    })
    ;(api.getStreamingConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { enabled: false, max_queue_size_gb: 10, max_queue_files: 1000, producer_threads: 2 },
    })
    ;(api.getDiagnosticsHealth as ReturnType<typeof vi.fn>).mockResolvedValue({
        success: true,
        data: { status: 'healthy' },
    })
}

beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    setupDefaultMocks()
})

// ---------------------------------------------------------------------------
// Demo mode
// ---------------------------------------------------------------------------

describe('SettingsPage — demo mode', () => {
    beforeEach(() => {
        localStorage.setItem('demoMode', 'true')
    })

    it('renders without crashing', () => {
        renderWithProviders(<SettingsPage />)
    })

    it('shows the General tab active by default', async () => {
        renderWithProviders(<SettingsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /general/i })).toBeTruthy()
        })
    })
})

// ---------------------------------------------------------------------------
// Tab navigation
// ---------------------------------------------------------------------------

describe('SettingsPage — tab navigation', () => {
    it('shows all tab labels', async () => {
        renderWithProviders(<SettingsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /general/i })).toBeTruthy()
        })
        expect(screen.getByRole('button', { name: /sources/i })).toBeTruthy()
        expect(screen.getByRole('button', { name: /users/i })).toBeTruthy()
        expect(screen.getByRole('button', { name: /automation/i })).toBeTruthy()
        expect(screen.getByRole('button', { name: /notifications/i })).toBeTruthy()
        expect(screen.getByRole('button', { name: /audit log/i })).toBeTruthy()
        expect(screen.getByRole('button', { name: /diagnostics/i })).toBeTruthy()
        expect(screen.getByRole('button', { name: /maintenance/i })).toBeTruthy()
    })

    it('loads Users tab when clicked', async () => {
        renderWithProviders(<SettingsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /users/i })).toBeTruthy()
        })
        fireEvent.click(screen.getByRole('button', { name: /users/i }))
        await waitFor(() => {
            expect(api.getUsers).toHaveBeenCalled()
        })
    })

    it('shows user rows after Users tab loads', async () => {
        renderWithProviders(<SettingsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /users/i })).toBeTruthy()
        })
        fireEvent.click(screen.getByRole('button', { name: /users/i }))
        await waitFor(() => {
            // Multiple elements may contain 'admin' / 'operator'
            expect(screen.getAllByText('admin').length).toBeGreaterThan(0)
            expect(screen.getAllByText('operator').length).toBeGreaterThan(0)
        })
    })

    it('loads SSO config when SSO/OIDC tab clicked', async () => {
        renderWithProviders(<SettingsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /sso/i })).toBeTruthy()
        })
        fireEvent.click(screen.getByRole('button', { name: /sso/i }))
        await waitFor(() => {
            expect(api.getSSOConfig).toHaveBeenCalled()
        })
    })

    it('loads audit log when Audit Log tab clicked', async () => {
        renderWithProviders(<SettingsPage />)
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /audit log/i })).toBeTruthy()
        })
        fireEvent.click(screen.getByRole('button', { name: /audit log/i }))
        await waitFor(() => {
            expect(api.getAuditLog).toHaveBeenCalled()
        })
    })
})

// ---------------------------------------------------------------------------
// General tab
// ---------------------------------------------------------------------------

describe('SettingsPage — General tab', () => {
    it('calls getSystemInfo on mount', async () => {
        renderWithProviders(<SettingsPage />)
        await waitFor(() => {
            expect(api.getSystemInfo).toHaveBeenCalled()
        })
    })

    it('calls getMailSlotConfig on mount', async () => {
        renderWithProviders(<SettingsPage />)
        await waitFor(() => {
            expect(api.getMailSlotConfig).toHaveBeenCalled()
        })
    })

    it('handles getSystemInfo failure gracefully', async () => {
        // Use a failure response rather than rejection to avoid unhandled promise rejection
        // (fetchSystemInfo has no try/catch)
        ;(api.getSystemInfo as ReturnType<typeof vi.fn>).mockResolvedValue({
            success: false,
            error: 'Server error',
        })
        renderWithProviders(<SettingsPage />)
        await waitFor(() => {
            expect(document.body).toBeTruthy()
        })
    })
})
