<script setup lang="ts">
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, ScatterChart, RadarChart } from 'echarts/charts'
import {
  GridComponent, TooltipComponent, LegendComponent,
  MarkAreaComponent, MarkLineComponent, DataZoomComponent, GraphicComponent,
  RadarComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'

use([
  CanvasRenderer, LineChart, BarChart, ScatterChart, RadarChart,
  GridComponent, TooltipComponent, LegendComponent,
  MarkAreaComponent, MarkLineComponent, DataZoomComponent, GraphicComponent,
  RadarComponent,
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
