<script setup lang="ts">
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  MarkAreaComponent, MarkLineComponent, DataZoomComponent, GraphicComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'

// RadarChart + RadarComponent are NOT registered here — they're lazy-loaded
// only by RealEstate.vue (the only page using radar), keeping them out of the
// shared vendor-echarts chunk.
use([
  CanvasRenderer, LineChart, BarChart, ScatterChart,
  GridComponent, TooltipComponent, LegendComponent,
  MarkAreaComponent, MarkLineComponent, DataZoomComponent, GraphicComponent,
])

defineProps<{ option: Record<string, any>; height?: string }>()
</script>

<template>
  <VChart
    :option="option"
    :style="{ height: height ?? '320px', width: '100%' }"
    autoresize
  />
</template>
