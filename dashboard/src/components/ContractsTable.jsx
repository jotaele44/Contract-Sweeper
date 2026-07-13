import { useMemo, useState } from 'react'
import { useContracts } from '@/lib/hooks'
import {
  Table, TableHeader, TableBody, TableRow, TableCell,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import QueryBoundary from '@/components/QueryBoundary'
import DetailRow from '@/components/DetailRow'
import SortHead from '@/components/SortHead'
import { fmtMoney, statusTone } from '@/lib/cs-format'
import { useSortable } from '@/lib/use-sortable'
import { cn } from '@/lib/utils'

export default function ContractsTable() {
  const query = useContracts()
  const contracts = query.data ?? []
  const [agency, setAgency] = useState('')
  const [open, setOpen] = useState(null)

  const filtered = useMemo(
    () => (agency
      ? contracts.filter((c) => (c.awardingName || '').toLowerCase().includes(agency.toLowerCase()))
      : contracts),
    [contracts, agency],
  )
  const { sorted: rows, sort, key, dir } = useSortable(filtered)
  const sorter = { sort, key, dir }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 p-2">
        <span className="text-xs text-muted-foreground">{rows.length} contracts</span>
        <Input
          value={agency} onChange={(e) => setAgency(e.target.value)}
          placeholder="Filter by awarding agency…"
          className="h-7 w-[240px] bg-background text-xs"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <QueryBoundary query={query} isEmpty={(d) => !d?.length} emptyLabel="No contracts">
          <Table>
            <TableHeader className="sticky top-0 bg-card">
              <TableRow className="border-border hover:bg-transparent">
                <SortHead sortKey="contractNumber" sorter={sorter}>Contract</SortHead>
                <SortHead sortKey="awardingName" sorter={sorter}>Awarding</SortHead>
                <SortHead sortKey="contractorName" sorter={sorter}>Contractor</SortHead>
                <SortHead sortKey="municipality" sorter={sorter}>Municipio</SortHead>
                <SortHead sortKey="awardAmount" sorter={sorter} align="right" className="text-right">Amount</SortHead>
                <SortHead sortKey="status" sorter={sorter}>Status</SortHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((c) => (
                <TableRow
                  key={c.contractId}
                  role="button"
                  tabIndex={0}
                  onClick={() => setOpen(c)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(c) } }}
                  className="cursor-pointer border-border hover:bg-muted/50 focus:bg-muted/50 focus:outline-none"
                >
                  <TableCell className="max-w-[160px] truncate text-xs text-foreground">{c.contractNumber || c.contractId}</TableCell>
                  <TableCell className="max-w-[160px] truncate text-xs text-foreground/80">{c.awardingName || '—'}</TableCell>
                  <TableCell className="max-w-[160px] truncate text-xs text-foreground/80">{c.contractorName || '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{c.municipality || '—'}</TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums text-foreground">{fmtMoney(c.awardAmount)}</TableCell>
                  <TableCell><Badge variant="outline" className={cn('text-[10px]', statusTone(c.status))}>{c.status}</Badge></TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow><TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">No contracts match</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </QueryBoundary>
      </div>

      <Sheet open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent className="w-full overflow-y-auto border-border bg-background text-foreground sm:max-w-md">
          {open && (
            <>
              <SheetHeader>
                <Badge variant="outline" className={cn('w-fit text-[10px]', statusTone(open.status))}>{open.status}</Badge>
                <SheetTitle className="text-left text-foreground">{open.serviceType || open.contractNumber}</SheetTitle>
                <SheetDescription className="text-left text-muted-foreground">{open.contractNumber} · {open.contractId}</SheetDescription>
              </SheetHeader>
              <dl className="mt-4 space-y-2 text-sm">
                <DetailRow k="Awarding entity" v={open.awardingName} />
                <DetailRow k="Contractor" v={open.contractorName} />
                <DetailRow k="Municipality" v={open.municipality} />
                <DetailRow k="Award amount" v={fmtMoney(open.awardAmount)} />
                <DetailRow k="Period" v={`${open.startDate || '?'} → ${open.endDate || '?'}`} />
                <DetailRow k="Fiscal year" v={open.fiscalYear} />
                <DetailRow k="Confidence" v={open.confidence} />
              </dl>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
