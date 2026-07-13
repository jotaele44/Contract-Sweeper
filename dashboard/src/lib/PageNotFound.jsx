import { useLocation, useNavigate } from 'react-router-dom'

// Auth-stripped 404 (no base44 auth lookup).
export default function PageNotFound() {
  const location = useLocation()
  const navigate = useNavigate()
  const pageName = location.pathname.substring(1)

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <div className="w-full max-w-md space-y-6 text-center">
        <div className="space-y-2">
          <h1 className="text-7xl font-light text-muted-foreground/50">404</h1>
          <div className="mx-auto h-0.5 w-16 bg-border"></div>
        </div>
        <div className="space-y-3">
          <h2 className="text-2xl font-medium text-foreground">Page Not Found</h2>
          <p className="leading-relaxed text-muted-foreground">
            The page <span className="font-medium text-foreground/80">&quot;{pageName}&quot;</span> could not be found.
          </p>
        </div>
        <div className="pt-2">
          <button
            onClick={() => navigate('/')}
            className="glow-border inline-flex items-center rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
          >
            Go Home
          </button>
        </div>
      </div>
    </div>
  )
}
