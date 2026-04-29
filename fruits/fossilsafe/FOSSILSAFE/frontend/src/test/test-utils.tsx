/**
 * Shared test utilities for FossilSafe frontend tests.
 *
 * Wraps components with all required providers so individual test files
 * don't need to repeat the boilerplate.
 */
import { ReactElement, ReactNode } from 'react'
import { render, RenderOptions } from '@testing-library/react'
import { MemoryRouter, MemoryRouterProps } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '@/contexts/AuthContext'
import { DemoModeProvider } from '@/lib/demoMode'
import { ToastProvider } from '@/contexts/ToastContext'

// ------------------------------------------------------------------
// Provider wrapper
// ------------------------------------------------------------------

function makeQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    })
}

interface WrapperOptions {
    /** Initial URL path for router */
    initialEntries?: MemoryRouterProps['initialEntries']
    /** Provide a pre-built QueryClient to share between tests */
    queryClient?: QueryClient
}

function AllProviders({
    children,
    initialEntries = ['/'],
    queryClient,
}: WrapperOptions & { children: ReactNode }) {
    const qc = queryClient ?? makeQueryClient()
    return (
        <MemoryRouter initialEntries={initialEntries}>
            <QueryClientProvider client={qc}>
                <AuthProvider>
                    <DemoModeProvider>
                        <ToastProvider>
                            {children}
                        </ToastProvider>
                    </DemoModeProvider>
                </AuthProvider>
            </QueryClientProvider>
        </MemoryRouter>
    )
}

// ------------------------------------------------------------------
// Custom render
// ------------------------------------------------------------------

type CustomRenderOptions = Omit<RenderOptions, 'wrapper'> & WrapperOptions

export function renderWithProviders(
    ui: ReactElement,
    { initialEntries, queryClient, ...renderOptions }: CustomRenderOptions = {},
) {
    const Wrapper = ({ children }: { children: ReactNode }) => (
        <AllProviders initialEntries={initialEntries} queryClient={queryClient}>
            {children}
        </AllProviders>
    )
    return render(ui, { wrapper: Wrapper, ...renderOptions })
}

// Re-export everything from @testing-library/react for convenience
export * from '@testing-library/react'
