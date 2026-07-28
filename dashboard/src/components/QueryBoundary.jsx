import { useEffect, useState } from 'react'
import {
  FederationButton,
  FederationDegradedState,
  FederationEmptyState,
  FederationErrorState,
  FederationFilteredEmptyState,
  FederationLoadingState,
  FederationOfflineState,
  FederationPanel,
  FederationStaleDataState,
} from '@pr-federation/react'
import { AlertTriangle, Clock3, Inbox, SearchX, WifiOff } from 'lucide-react'

const DEFAULT_STALE_AFTER_MS = 5 * 60 * 1000

function evaluate(value, data) {
  return typeof value === 'function' ? Boolean(value(data)) : Boolean(value)
}

function readBrowserOnline() {
  return typeof navigator === 'undefined' || navigator.onLine !== false
}

function useBrowserOnline() {
  const [online, setOnline] = useState(readBrowserOnline)

  useEffect(() => {
    if (typeof window === 'undefined') return undefined

    const update = () => setOnline(readBrowserOnline())
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])

  return online
}

function useStaleDeadline(dataUpdatedAt, staleAfterMs) {
  const [, setDeadlineTick] = useState(0)

  useEffect(() => {
    if (!dataUpdatedAt || staleAfterMs <= 0) return undefined

    const delay = dataUpdatedAt + staleAfterMs - Date.now()
    if (delay <= 0) return undefined

    const timer = setTimeout(() => setDeadlineTick((value) => value + 1), delay + 25)
    return () => clearTimeout(timer)
  }, [dataUpdatedAt, staleAfterMs])
}

function StatePanel({ children }) {
  return (
    <FederationPanel className="ms-panel-reset h-full border-0 bg-transparent shadow-none">
      {children}
    </FederationPanel>
  )
}

function RetryAction({ onRetry, label = 'Retry' }) {
  return (
    <FederationButton variant="secondary" onClick={onRetry}>
      {label}
    </FederationButton>
  )
}

export default function QueryBoundary({
  query,
  isEmpty,
  isFilteredEmpty = false,
  emptyLabel = 'Nothing to show',
  filteredEmptyLabel = 'No matching records',
  filteredEmptyDescription = 'Adjust or clear the active filters.',
  onResetFilters,
  staleAfterMs = DEFAULT_STALE_AFTER_MS,
  children,
}) {
  const {
    data,
    dataUpdatedAt = 0,
    error,
    fetchStatus,
    isError,
    isFetching,
    isLoading,
    isPending,
    isStale,
    refetch,
  } = query

  const browserOnline = useBrowserOnline()
  useStaleDeadline(dataUpdatedAt, staleAfterMs)

  const empty = evaluate(isEmpty ?? ((value) => !value), data)
  const filteredEmpty = !empty && evaluate(isFilteredEmpty, data)
  const offline = fetchStatus === 'paused' || !browserOnline
  const loading = Boolean((isPending || isLoading) && data == null)
  const stale = Boolean(
    !offline && !isError && !isFetching && isStale && dataUpdatedAt > 0 && Date.now() - dataUpdatedAt >= staleAfterMs,
  )
  const retry = () => refetch()

  const banner = offline ? (
    <FederationOfflineState
      inline
      className="ms-state-banner"
      icon={<WifiOff className="h-4 w-4" />}
      title="Offline — showing cached data"
      description="Reconnect to refresh this view."
      action={<RetryAction onRetry={retry} />}
    />
  ) : isError ? (
    <FederationDegradedState
      inline
      className="ms-state-banner"
      icon={<AlertTriangle className="h-4 w-4" />}
      title="Refresh failed — showing the last successful result"
      action={<RetryAction onRetry={retry} />}
    />
  ) : stale ? (
    <FederationStaleDataState
      inline
      className="ms-state-banner"
      icon={<Clock3 className="h-4 w-4" />}
      title="This view may be stale"
      description="Refresh to check for newer records."
      action={<RetryAction onRetry={retry} label="Refresh" />}
    />
  ) : null

  // A first load while offline is both pending and paused. Offline must win or
  // the view remains on a loading indicator that cannot complete.
  if (offline && empty) {
    return (
      <StatePanel>
        <FederationOfflineState
          className="h-full content-center"
          icon={<WifiOff className="h-5 w-5" />}
          title="MoneySweep is offline"
          description="Reconnect to load records that are not already cached."
          action={<RetryAction onRetry={retry} />}
        />
      </StatePanel>
    )
  }

  if (loading) {
    return (
      <StatePanel>
        <FederationLoadingState
          className="h-full content-center"
          title="Loading records"
          description="Retrieving the latest MoneySweep data."
        />
      </StatePanel>
    )
  }

  if (isError && empty) {
    return (
      <StatePanel>
        <FederationErrorState
          className="h-full content-center"
          icon={<AlertTriangle className="h-5 w-5" />}
          title="Couldn’t reach the backend"
          description={error?.message ? 'The request failed. Retry when the service is available.' : 'Retry when the service is available.'}
          action={<RetryAction onRetry={retry} />}
        />
      </StatePanel>
    )
  }

  if (empty) {
    return (
      <StatePanel>
        <FederationEmptyState
          className="h-full content-center"
          icon={<Inbox className="h-5 w-5" />}
          title={emptyLabel}
        />
      </StatePanel>
    )
  }

  if (filteredEmpty) {
    return (
      <>
        {banner}
        <StatePanel>
          <FederationFilteredEmptyState
            className="h-full content-center"
            icon={<SearchX className="h-5 w-5" />}
            title={filteredEmptyLabel}
            description={filteredEmptyDescription}
            action={onResetFilters ? <RetryAction onRetry={onResetFilters} label="Clear filters" /> : undefined}
          />
        </StatePanel>
      </>
    )
  }

  return (
    <>
      {banner}
      {children}
    </>
  )
}
