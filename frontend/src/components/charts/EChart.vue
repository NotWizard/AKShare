<script setup lang="ts">
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, ScatterChart } from 'echarts/charts'
import {
  AriaComponent, GridComponent, TooltipComponent, LegendComponent,
  MarkAreaComponent, MarkLineComponent, DataZoomComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { computed, markRaw } from 'vue'
import type { EChartsOption } from 'echarts'

// RadarChart + RadarComponent are NOT registered here — they're lazy-loaded
// only by RealEstate.vue (the only page using radar), keeping them out of the
// shared vendor-echarts chunk.
// GraphicComponent was removed — the `graphic:` text-overlay it powered was
// deleted when the M2 gap-marker was dropped (charts start at 1996-12 now).
use([
  CanvasRenderer, LineChart, BarChart, ScatterChart,
  AriaComponent, GridComponent, TooltipComponent, LegendComponent,
  MarkAreaComponent, MarkLineComponent, DataZoomComponent,
])

const props = defineProps<{ option: EChartsOption; height?: string; notMerge?: boolean }>()

// markRaw → vue-echarts deep-watches `option`; wrapping it keeps Vue from
// traversing/proxying the (up to ~3000-point) series graph on every tick.
// notMerge:false → ECharts merges each rebuilt option into the SAME instance
// instead of tearing the coordinate system down, so the dataZoom range and
// legend selection survive data refreshes. lazyUpdate batches the redraw.
// notMerge=true is required for charts whose series COUNT varies with the data
// (per-phase scatter/quadrant): merge-by-index would leave ghost series when the
// visible phase set shrinks. Those charts have value axes / no dataZoom, so a
// full rebuild loses no interaction state.
const rawOption = computed(() => markRaw(props.option))
const updateOptions = computed(() => ({ notMerge: props.notMerge ?? false, lazyUpdate: true }))
</script>

<template>
  <VChart
    :option="rawOption"
    :update-options="updateOptions"
    :style="{ height: height ?? '320px', width: '100%' }"
    autoresize
  />
</template>
