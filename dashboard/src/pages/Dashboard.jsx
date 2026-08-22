import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import StatsBar from '@/components/StatsBar'
import ContractsTable from '@/components/ContractsTable'
import EntitiesTable from '@/components/EntitiesTable'
import RelationshipGraph from '@/components/RelationshipGraph'
import MunicipalityAggregates from '@/components/MunicipalityAggregates'
import CampaignFinance from '@/components/CampaignFinance'
import GovernmentChanges from '@/components/GovernmentChanges'
import brandMark from "@/assets/icon-64.png?inline";

const TABS = ['contracts', 'entities', 'government-changes', 'graph', 'municipios', 'campaign-finance']

export default function Dashboard() {
  const [params, setParams] = useSearchParams()
  const tab = TABS.includes(params.get('tab')) ? params.get('tab') : 'contracts'
  const setTab = (value) => setParams((prev) => {
    prev.set('tab', value)
    return prev
  }, { replace: true })

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="panel-glass flex items-center gap-2 border-b border-border px-4 py-2.5">
        <img src={brandMark} alt="" aria-hidden="true" className="h-6 w-6 rounded-md" />
        <div>
          <h1 className="text-sm font-semibold leading-none text-foreground">moneysweep-pr</h1>
          <p className="mt-0.5 text-[11px] text-muted-foreground">Puerto Rico public-money contracts, entities &amp; campaign finance</p>
        </div>
      </header>

      <StatsBar />

      <div className="min-h-0 flex-1 p-3">
        <Tabs value={tab} onValueChange={setTab} className="flex h-full flex-col">
          <TabsList className="grid w-full grid-cols-6 bg-card">
            <TabsTrigger value="contracts" className="text-xs data-[state=active]:glow-border">Contracts</TabsTrigger>
            <TabsTrigger value="entities" className="text-xs data-[state=active]:glow-border">Entities</TabsTrigger>
            <TabsTrigger value="government-changes" className="text-xs data-[state=active]:glow-border">Gov Changes</TabsTrigger>
            <TabsTrigger value="graph" className="text-xs data-[state=active]:glow-border">Relationships</TabsTrigger>
            <TabsTrigger value="municipios" className="text-xs data-[state=active]:glow-border">Municipios</TabsTrigger>
            <TabsTrigger value="campaign-finance" className="text-xs data-[state=active]:glow-border">Campaign Finance</TabsTrigger>
          </TabsList>
          <div className="mt-3 min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-background/40">
            <TabsContent value="contracts" className="m-0 h-full"><ContractsTable /></TabsContent>
            <TabsContent value="entities" className="m-0 h-full"><EntitiesTable /></TabsContent>
            <TabsContent value="government-changes" className="m-0 h-full"><GovernmentChanges /></TabsContent>
            <TabsContent value="graph" className="m-0 h-full"><RelationshipGraph /></TabsContent>
            <TabsContent value="municipios" className="m-0 h-full"><MunicipalityAggregates /></TabsContent>
            <TabsContent value="campaign-finance" className="m-0 h-full"><CampaignFinance /></TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  )
}
