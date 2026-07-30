import { useQuery } from '@tanstack/react-query'
import {
  getHealth, getContracts, getEntities, getEdges, getMunicipalities, getStats,
  getCampaignFinanceSummary, getCampaignFinanceContributions,
  getCampaignFinanceEntities, getCampaignFinanceReports,
} from '@/lib/api'

export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 15_000 })
export const useStats = () => useQuery({ queryKey: ['stats'], queryFn: getStats })
export const useContracts = (filters = {}) =>
  useQuery({ queryKey: ['contracts', filters], queryFn: () => getContracts(filters) })
export const useEntities = (filters = {}) =>
  useQuery({ queryKey: ['entities', filters], queryFn: () => getEntities(filters) })
export const useEdges = (filters = {}) =>
  useQuery({ queryKey: ['edges', filters], queryFn: () => getEdges(filters) })
export const useMunicipalities = () => useQuery({ queryKey: ['municipalities'], queryFn: getMunicipalities })

export const useCampaignFinanceSummary = () =>
  useQuery({ queryKey: ['campaign-finance-summary'], queryFn: getCampaignFinanceSummary })
export const useCampaignFinanceContributions = (filters = {}) =>
  useQuery({
    queryKey: ['campaign-finance-contributions', filters],
    queryFn: () => getCampaignFinanceContributions(filters),
  })
export const useCampaignFinanceEntities = (filters = {}) =>
  useQuery({
    queryKey: ['campaign-finance-entities', filters],
    queryFn: () => getCampaignFinanceEntities(filters),
  })
export const useCampaignFinanceReports = (filters = {}) =>
  useQuery({
    queryKey: ['campaign-finance-reports', filters],
    queryFn: () => getCampaignFinanceReports(filters),
  })
