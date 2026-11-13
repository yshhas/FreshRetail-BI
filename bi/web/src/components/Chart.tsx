import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

export function Chart({
  option, height = 320, onEvents
}: { option: EChartsOption; height?: number; onEvents?: Record<string, (p: unknown) => void> }) {
  return (
    <ReactECharts
      option={{ animation: false, ...option }}
      style={{ height }}
      notMerge
      lazyUpdate={false}
      onEvents={onEvents}
    />
  )
}
