// Shared key/value row for the entity/contract detail sheets.
export default function DetailRow({ k, v }) {
  return (
    <div className="flex justify-between gap-4 border-b border-border/60 pb-1.5">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="text-right text-foreground">{v ?? '—'}</dd>
    </div>
  )
}
