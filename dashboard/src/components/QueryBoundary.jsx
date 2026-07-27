import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { AlertTriangle, Inbox } from 'lucide-react'
import { FederationEmptyState } from '@pr-federation/react'

// One place for the three non-happy states every data tab shares: loading,
// error (with retry), and empty. Pass a react-query result plus an `isEmpty`
// predicate; children render only once data is present and non-empty.
export default function QueryBoundary({ query, isEmpty, emptyLabel = 'Nothing to show', children }) {
  const { isLoading, isError, refetch, data } = query

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2 p-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full bg-muted/60" />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <AlertTriangle className="h-6 w-6 text-destructive" />
        <p className="text-sm text-muted-foreground">Couldn’t reach the backend.</p>
        <Button size="sm" variant="outline" className="glow-border" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    )
  }

  if (typeof isEmpty === 'function' ? isEmpty(data) : !data) {
    // Shared federation empty state (@pr-federation/react) so every data tab's
    // "nothing to show" reads identically across the federation. `content-center`
    // keeps it vertically centered — .fd-empty-state is a grid and would
    // otherwise pin to the top of the full-height panel.
    return (
      <FederationEmptyState
        className="h-full content-center"
        icon={<Inbox className="h-5 w-5" />}
        title={emptyLabel}
      />
    )
  }

  return children
}
