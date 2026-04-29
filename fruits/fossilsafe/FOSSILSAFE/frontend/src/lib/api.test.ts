/**
 * Comprehensive tests for ApiClient (api.ts).
 *
 * Strategy: mock global.fetch; check that the right URL, method, and body
 * are used for each API method; verify the normalised ApiResponse shape.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from './api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetchOk(payload: unknown) {
    ;(fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve(payload),
    })
}

function mockFetchError(status: number, payload: unknown) {
    ;(fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: false,
        status,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve(payload),
    })
}

function lastCallUrl() {
    const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls
    return calls[calls.length - 1][0] as string
}

function lastCallOptions() {
    const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls
    return calls[calls.length - 1][1] as RequestInit
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
    vi.clearAllMocks()
    // Reset fetch to clear any queued mockResolvedValueOnce values from previous tests
    ;(fetch as ReturnType<typeof vi.fn>).mockReset()
    localStorage.clear()
    // Default: return 200 with an empty success response
    ;(fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve({ success: true, data: {} }),
    })
})

// ---------------------------------------------------------------------------
// GET requests
// ---------------------------------------------------------------------------

describe('GET requests', () => {
    it('getSetupStatus hits /api/auth/setup-status', async () => {
        mockFetchOk({ success: true, data: { setup_required: false } })
        const res = await api.getSetupStatus()
        expect(res.success).toBe(true)
        expect(lastCallUrl()).toContain('/api/auth/setup-status')
        // method may be undefined (fetch default GET) or explicitly 'GET'
        expect(lastCallOptions().method ?? 'GET').toBe('GET')
    })

    it('getJobs passes limit and offset as query params', async () => {
        mockFetchOk({ success: true, data: { jobs: [], total: 0 } })
        await api.getJobs(50, 10)
        expect(lastCallUrl()).toContain('limit=50')
        expect(lastCallUrl()).toContain('offset=10')
    })

    it('getTapes normalises slot_number for slot tapes', async () => {
        mockFetchOk({
            success: true,
            data: {
                tapes: [
                    { barcode: 'TAPE01', location_type: 'slot', slot: 5, slot_number: undefined },
                    { barcode: 'TAPE02', location_type: 'drive', slot: 1, slot_number: 1 },
                ],
            },
        })
        const res = await api.getTapes()
        expect(res.success).toBe(true)
        // Slot tape: slot_number taken from 'slot' field
        expect(res.data?.tapes[0].slot_number).toBe(5)
        // Drive tape: slot_number cleared to undefined
        expect(res.data?.tapes[1].slot_number).toBeUndefined()
    })

    it('getSystemStats hits /api/system/stats', async () => {
        mockFetchOk({ success: true, data: { cpu_percent: 42 } })
        const res = await api.getSystemStats()
        expect(res.success).toBe(true)
        expect(lastCallUrl()).toContain('/api/system/stats')
    })

    it('getHealth hits /api/healthz', async () => {
        mockFetchOk({ success: true, data: { status: 'ok', version: '1.0.0' } })
        await api.getHealth()
        expect(lastCallUrl()).toContain('/api/healthz')
    })

    it('getDriveHealth hits /api/drive/health', async () => {
        mockFetchOk({ success: true, data: { drives: [] } })
        await api.getDriveHealth()
        expect(lastCallUrl()).toContain('/api/drive/health')
    })

    it('getSchedules hits /api/schedules', async () => {
        mockFetchOk({ success: true, data: { schedules: [] } })
        await api.getSchedules()
        expect(lastCallUrl()).toContain('/api/schedules')
    })

    it('getAuditLog passes limit and offset', async () => {
        mockFetchOk({ success: true, data: { entries: [], limit: 20, offset: 5 } })
        await api.getAuditLog(20, 5)
        expect(lastCallUrl()).toContain('limit=20')
        expect(lastCallUrl()).toContain('offset=5')
    })

    it('getMe hits /api/auth/me', async () => {
        mockFetchOk({ success: true, data: { username: 'admin' } })
        await api.getMe()
        expect(lastCallUrl()).toContain('/api/auth/me')
    })

    it('getSSOConfig hits /api/auth/sso/config', async () => {
        mockFetchOk({ success: true, data: { enabled: false, issuer: '' } })
        await api.getSSOConfig()
        expect(lastCallUrl()).toContain('/api/auth/sso/config')
    })

    it('getTapeDetails constructs URL from barcode', async () => {
        mockFetchOk({ success: true, data: { tape: { barcode: 'ABC123' } } })
        await api.getTapeDetails('ABC123')
        expect(lastCallUrl()).toContain('/api/tapes/ABC123')
    })

    it('getMailSlotConfig hits /api/system/mailslots', async () => {
        mockFetchOk({ success: true, data: { enabled: true, auto_detect: true } })
        await api.getMailSlotConfig()
        expect(lastCallUrl()).toContain('/api/system/mailslots')
    })

    it('getRestoreJobs hits /api/restore/jobs', async () => {
        mockFetchOk({ success: true, data: { jobs: [] } })
        await api.getRestoreJobs(25)
        expect(lastCallUrl()).toContain('/api/restore/jobs')
        expect(lastCallUrl()).toContain('limit=25')
    })

    it('getUsers hits /api/auth/users', async () => {
        mockFetchOk({ success: true, data: { users: [] } })
        await api.getUsers()
        expect(lastCallUrl()).toContain('/api/auth/users')
    })
})

// ---------------------------------------------------------------------------
// POST requests (CSRF flow)
// ---------------------------------------------------------------------------

describe('POST requests', () => {
    // The client fetches a CSRF token before every POST.
    function mockCsrfThenOk(postPayload: unknown) {
        ;(fetch as ReturnType<typeof vi.fn>)
            .mockResolvedValueOnce({
                ok: true,
                status: 200,
                headers: { get: () => 'application/json' },
                json: () => Promise.resolve({ csrf_token: 'test-token' }),
            })
            .mockResolvedValueOnce({
                ok: true,
                status: 200,
                headers: { get: () => 'application/json' },
                json: () => Promise.resolve(postPayload),
            })
    }

    it('cleanupLogs sends retention_days and gets deleted_count', async () => {
        mockCsrfThenOk({ success: true, data: { deleted_count: 99 } })
        const res = await api.cleanupLogs(7)
        expect(res.success).toBe(true)
        expect(res.data?.deleted_count).toBe(99)
        const opts = lastCallOptions()
        expect(opts.method).toBe('POST')
        expect(JSON.parse(opts.body as string)).toEqual({ retention_days: 7 })
    })

    it('unloadTape sends drive index', async () => {
        mockCsrfThenOk({ success: true, message: 'ok' })
        await api.unloadTape(1)
        expect(lastCallUrl()).toContain('/api/library/unload')
        expect(JSON.parse(lastCallOptions().body as string)).toEqual({ drive: 1 })
    })

    it('wipeTape sends barcode, drive, and erase_mode', async () => {
        mockCsrfThenOk({ success: true, data: { job_id: 7 } })
        const res = await api.wipeTape('TAPE01', 0, 'quick')
        expect(res.data?.job_id).toBe(7)
        expect(lastCallUrl()).toContain('/api/tapes/TAPE01/wipe')
        const body = JSON.parse(lastCallOptions().body as string)
        expect(body.confirmation).toBe('TAPE01')
        expect(body.erase_mode).toBe('quick')
    })

    it('cancelJob hits /api/jobs/:id/cancel', async () => {
        mockCsrfThenOk({ success: true })
        await api.cancelJob(42)
        expect(lastCallUrl()).toContain('/api/jobs/42/cancel')
        expect(lastCallOptions().method).toBe('POST')
    })

    it('createJob sends job data and returns job_id', async () => {
        mockCsrfThenOk({ success: true, data: { job_id: 101 } })
        const res = await api.createJob({ name: 'My Backup', type: 'backup' })
        expect(res.data?.job_id).toBe(101)
        const body = JSON.parse(lastCallOptions().body as string)
        expect(body.name).toBe('My Backup')
    })

    it('scanLibrary sends mode and returns tapes', async () => {
        mockCsrfThenOk({ success: true, data: { tapes: [] } })
        await api.scanLibrary('deep')
        expect(lastCallUrl()).toContain('/api/tapes/scan')
        expect(JSON.parse(lastCallOptions().body as string)).toEqual({ mode: 'deep' })
    })

    it('formatTape sends drive', async () => {
        mockCsrfThenOk({ success: true, data: { job_id: 5 } })
        await api.formatTape('TAPE01', 0)
        expect(lastCallUrl()).toContain('/api/tapes/TAPE01/format')
        expect(JSON.parse(lastCallOptions().body as string)).toEqual({ drive: 0 })
    })

    it('updateTapeAlias sends alias', async () => {
        mockCsrfThenOk({ success: true, data: { alias: 'MyArchive' } })
        await api.updateTapeAlias('TAPE01', 'MyArchive')
        expect(lastCallUrl()).toContain('/api/tapes/TAPE01/alias')
        expect(JSON.parse(lastCallOptions().body as string)).toEqual({ alias: 'MyArchive' })
    })

    it('updateTapeAlias sends null to clear an alias', async () => {
        mockCsrfThenOk({ success: true, data: { alias: null } })
        await api.updateTapeAlias('TAPE01', null)
        const body = JSON.parse(lastCallOptions().body as string)
        expect(body.alias).toBeNull()
    })

    it('loadTape builds the right URL with drive', async () => {
        mockCsrfThenOk({ success: true, message: 'loading' })
        await api.loadTape('TAPE01', 1)
        expect(lastCallUrl()).toContain('/api/library/load/TAPE01')
        expect(lastCallUrl()).toContain('drive=1')
    })

    it('verifyAuditChain hits /api/audit/verify', async () => {
        mockCsrfThenOk({ success: true, data: { valid: true, total_entries: 100, tampered_indices: [] } })
        const res = await api.verifyAuditChain()
        expect(res.success).toBe(true)
        expect(lastCallUrl()).toContain('/api/audit/verify')
    })

    it('createSchedule sends schedule data', async () => {
        const scheduleData = { name: 'Weekly', cron: '0 0 * * 0' }
        mockCsrfThenOk({ success: true, data: { schedule_id: 'sched-1' } })
        await api.createSchedule(scheduleData)
        const body = JSON.parse(lastCallOptions().body as string)
        expect(body.name).toBe('Weekly')
    })
})

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe('error handling', () => {
    it('returns success=false with error message on 400', async () => {
        mockFetchError(400, { error: 'Bad request', success: false })
        const res = await api.getSetupStatus()
        expect(res.success).toBe(false)
        expect(res.error).toBeTruthy()
    })

    it('returns success=false with "Session expired" on 401', async () => {
        mockFetchError(401, { error: 'Unauthorized' })
        const res = await api.getJobs()
        expect(res.success).toBe(false)
        expect(res.error).toBe('Session expired')
    })

    it('removes token from localStorage on 401', async () => {
        localStorage.setItem('token', 'stale-token')
        mockFetchError(401, { error: 'Unauthorized' })
        await api.getJobs()
        expect(localStorage.removeItem).toHaveBeenCalledWith('token')
    })

    it('returns success=false on network error', async () => {
        ;(fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network down'))
        const res = await api.getSetupStatus()
        expect(res.success).toBe(false)
        expect(res.error).toContain('Network down')
    })

    it('passes Authorization header when token is in localStorage', async () => {
        localStorage.setItem('token', 'test-bearer-token')
        mockFetchOk({ success: true, data: {} })
        await api.getJobs()
        const headers = lastCallOptions().headers as Record<string, string>
        expect(headers['Authorization']).toBe('Bearer test-bearer-token')
    })

    it('does not set Authorization header when no token', async () => {
        mockFetchOk({ success: true, data: {} })
        await api.getJobs()
        const headers = lastCallOptions().headers as Record<string, string>
        expect(headers['Authorization']).toBeUndefined()
    })
})

