import { useEffect, useState } from 'react'

type ApiStatus = 'checking' | 'online' | 'offline'

const statusStyles: Record<ApiStatus, string> = {
  checking: 'bg-slate-100 text-slate-600',
  online: 'bg-emerald-100 text-emerald-800',
  offline: 'bg-red-100 text-red-800',
}

export default function App() {
  const [status, setStatus] = useState<ApiStatus>('checking')

  useEffect(() => {
    const controller = new AbortController()
    fetch('/health/live', { signal: controller.signal })
      .then((res) => setStatus(res.ok ? 'online' : 'offline'))
      .catch(() => {
        if (!controller.signal.aborted) setStatus('offline')
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-16 text-slate-900">
      <div className="mx-auto max-w-xl">
        <h1 className="text-2xl font-semibold">HVAC AI Receptionist</h1>
        <p className="mt-2 text-slate-600">Owner dashboard: coming in Phase 7.</p>
        <p className="mt-6 text-sm">
          Backend API:{' '}
          <span className={`rounded px-2 py-0.5 font-medium ${statusStyles[status]}`}>{status}</span>
        </p>
      </div>
    </main>
  )
}
