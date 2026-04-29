import { BrowserRouter, Routes, Route } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import React, { useState, useEffect, ReactNode } from "react"
import AppLayout from "@/layouts/AppLayout"
import DashboardPage from "@/pages/DashboardPage"
import TapesPage from "@/pages/TapesPage"
import JobsPage from "@/pages/JobsPage"
import RestorePage from "@/pages/RestorePage"
import EquipmentPage from "@/pages/EquipmentPage"
import SettingsPage from "@/pages/SettingsPage"
import RecoveryPage from "@/pages/RecoveryPage"
import SchedulesPage from "@/pages/SchedulesPage"
import SelfTestPage from "@/pages/SelfTestPage"
import BackupSetsPage from "@/pages/BackupSetsPage"
import SetupWizard from "@/pages/SetupWizard"
import LoginPage from "@/pages/LoginPage"
import { AuthProvider, useAuth } from "@/contexts/AuthContext"
import { DemoModeProvider } from "@/lib/demoMode"
import { ToastProvider } from "@/contexts/ToastContext"
import { api } from "@/lib/api"

const queryClient = new QueryClient()

type AppState = 'loading' | 'setup' | 'login' | 'authenticated'

function AppContent() {
  const { isAuthenticated, isLoading, login } = useAuth()
  const [appState, setAppState] = useState<AppState>('loading')
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null)
  const [setupError, setSetupError] = useState<string | null>(null)

  useEffect(() => {
    let retryCount = 0
    const maxRetries = 5

    const checkSetupStatus = async () => {
      try {
        const res = await api.getSetupStatus()
        if (!res.success) {
          throw new Error(res.error || 'Backend error')
        }
        setSetupRequired(res.data?.setup_required ?? false)
        setSetupError(null)
      } catch (err) {
        console.error('Setup status check failed:', err)
        if (retryCount < maxRetries) {
          retryCount++
          console.log(`Retrying setup status check (${retryCount}/${maxRetries})...`)
          setTimeout(checkSetupStatus, 2000)
        } else {
          setSetupError(err instanceof Error ? err.message : 'Failed to contact FossilSafe backend')
        }
      }
    }
    checkSetupStatus()
  }, [])

  useEffect(() => {
    console.log('API PATCH ACTIVE: App mounted. Location:', window.location.pathname, window.location.search)
    console.log('AppState Effect:', { setupRequired, isAuthenticated, isLoading })
    if ((setupRequired === null && !setupError) || isLoading) {
      console.log('Setting AppState -> loading')
      setAppState('loading')
    } else if (setupRequired) {
      console.log('Setting AppState -> setup')
      setAppState('setup')
    } else if (!isAuthenticated) {
      console.log('Setting AppState -> login')
      setAppState('login')
    } else {
      console.log('Setting AppState -> authenticated')
      setAppState('authenticated')
    }
  }, [setupRequired, setupError, isAuthenticated, isLoading])

  const handleSetupComplete = (token: string, username: string, role: string) => {
    console.log('handleSetupComplete called', { token, username, role })
    setSetupRequired(false)
    login(token, { id: 0, username, role, has_2fa: false })
  }

  const handleLogin = (token: string, username: string, role: string) => {
    console.log('handleLogin called')
    login(token, { id: 0, username, role, has_2fa: false })
  }

  console.log('AppContent Render:', { appState, setupRequired, isAuthenticated, isLoading })

  if (appState === 'loading') {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="size-16 flex items-center justify-center rounded-lg bg-primary/10 border border-primary/20 overflow-hidden animate-pulse">
            <img src="/fossilsafe-logo.svg" alt="FossilSafe" className="size-14 object-contain" />
          </div>
          <div className="text-xs text-[#71717a] font-mono uppercase tracking-widest">Initializing...</div>
        </div>
      </div>
    )
  }

  if (setupError) {
    return (
      <div className="min-h-screen bg-[#09090b] flex items-center justify-center p-8">
        <div className="w-full max-w-md rounded-lg border border-[#27272a] bg-[#121214] p-8 shadow-2xl">
          <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-destructive mb-3">Backend Status</div>
          <h1 className="text-xl font-bold text-white mb-3">FossilSafe could not finish startup checks</h1>
          <p className="text-sm text-[#a1a1aa] mb-6">{setupError}</p>
          <button
            onClick={() => window.location.reload()}
            className="w-full py-3 bg-primary hover:bg-green-400 text-black font-bold rounded text-sm uppercase tracking-widest transition-all"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (appState === 'setup') {
    return <SetupWizard onComplete={handleSetupComplete} />
  }

  if (appState === 'login') {
    return <LoginPage onLogin={handleLogin} />
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/tapes" element={<TapesPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/schedules" element={<SchedulesPage />} />
          <Route path="/restore" element={<RestorePage />} />
          <Route path="/equipment" element={<EquipmentPage />} />
          <Route path="/self-test" element={<SelfTestPage />} />
          <Route path="/backup-sets" element={<BackupSetsPage />} />
          <Route path="/recovery" element={<RecoveryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

class ErrorBoundary extends React.Component<{ children: ReactNode }, { hasError: boolean, error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error("Uncaught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-black text-white p-8 flex flex-col items-center justify-center">
          <h1 className="text-2xl text-destructive mb-4">Application Crash</h1>
          <div id="error-boundary-message" className="bg-zinc-900 p-4 rounded border border-zinc-800 font-mono text-xs whitespace-pre-wrap max-w-2xl">
            {this.state.error?.toString()}
            <br />
            {this.state.error?.stack}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

import { SocketProvider } from "@/contexts/SocketProvider"

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <AuthProvider>
          <DemoModeProvider>
            <ToastProvider>
                <SocketProvider>
                  <AppContent />
                </SocketProvider>
              </ToastProvider>
          </DemoModeProvider>
        </AuthProvider>
      </ErrorBoundary>
    </QueryClientProvider>
  )
}

export default App
