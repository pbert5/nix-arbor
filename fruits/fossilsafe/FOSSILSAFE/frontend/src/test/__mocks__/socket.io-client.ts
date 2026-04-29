/**
 * Mock for socket.io-client — prevents real WebSocket connections in jsdom tests.
 */
import { vi } from 'vitest'

const mockSocket = {
    on: vi.fn(),
    off: vi.fn(),
    emit: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    connected: false,
    id: 'mock-socket-id',
}

export const io = vi.fn(() => mockSocket)
export default { io }
