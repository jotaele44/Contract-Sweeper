// Resolve a design-token CSS variable to a concrete color for libraries (recharts,
// inline SVG) that can't consume `var()` in presentation attributes.
export const hslVar = (name, alpha) => {
  if (typeof window === 'undefined') return undefined
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (!v) return undefined
  return alpha == null ? `hsl(${v})` : `hsl(${v} / ${alpha})`
}

export const CHART_SERIES = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5']
export const chartColor = (i) => hslVar(CHART_SERIES[i % CHART_SERIES.length])
