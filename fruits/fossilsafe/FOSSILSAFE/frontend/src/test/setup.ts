import '@testing-library/jest-dom'
import { vi } from 'vitest'

// ---------------------------------------------------------------------------
// socket.io-client: prevent real WebSocket connections in jsdom
// ---------------------------------------------------------------------------
vi.mock('socket.io-client', () => {
    const mockSocket = {
        on: vi.fn(),
        off: vi.fn(),
        emit: vi.fn(),
        connect: vi.fn(),
        disconnect: vi.fn(),
        connected: false,
        id: 'mock-socket-id',
    }
    return { io: vi.fn(() => mockSocket), default: { io: vi.fn(() => mockSocket) } }
})

// ---------------------------------------------------------------------------
// Global fetch stub (overridden per-test when needed)
// ---------------------------------------------------------------------------
global.fetch = vi.fn()

// ---------------------------------------------------------------------------
// localStorage stub (reset between tests via beforeEach in each file)
// ---------------------------------------------------------------------------
const _localStorageStore: Record<string, string> = {}
Object.defineProperty(global, 'localStorage', {
    value: {
        getItem: vi.fn((key: string) => _localStorageStore[key] ?? null),
        setItem: vi.fn((key: string, value: string) => { _localStorageStore[key] = value }),
        removeItem: vi.fn((key: string) => { delete _localStorageStore[key] }),
        clear: vi.fn(() => { Object.keys(_localStorageStore).forEach(k => delete _localStorageStore[k]) }),
    },
    writable: true,
})

