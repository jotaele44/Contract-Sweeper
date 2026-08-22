import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import QueryBoundary from '@/components/QueryBoundary'
import { useGovernmentChangeCandidates } from '@/lib/hooks'

export default function GovernmentChangeCandidates() {
  const query = useGovernmentChangeCandidates()
  const rows = query.data ?? []
  return (
    <QueryBoundary query={query} isEmpty={(data) => !data?.length} emptyLabel="No change candidates are materialized.">
      <Table>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.candidate_id}>
              <TableCell>{row.affected_entity_id}</TableCell>
              <TableCell>{row.candidate_event_type}</TableCell>
              <TableCell>{row.raw_match}</TableCell>
              <TableCell>{row.certification_state}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </QueryBoundary>
  )
}
