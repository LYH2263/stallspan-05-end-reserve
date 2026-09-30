<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
const vendors = ref<any[]>([])
async function run() { data.value = await api('/allocate/run?segment_id=1', { method: 'POST' }) }
onMounted(async () => {
  vendors.value = await api('/vendors')
  // 默认展示最近一次成功运行；旧 run 的边界以其快照为准，不被新应急值改写
  data.value = await api('/allocate/latest?segment_id=1')
})
const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']
const cells = computed(() => {
  if (!data.value) return []
  const width = data.value.segment.width_m
  const pct = (m: number) => (m / width) * 100
  const out: any[] = []
  // 禁入区间（应急带 + 挡柱，重叠已在引擎合并）——主图与引擎挖带同源同一套
  for (const b of data.value.blocked_spans || []) {
    const kinds = b.kinds || []
    const hasPillar = kinds.includes('pillar')
    const hasEm = kinds.includes('start_emergency') || kinds.includes('end_emergency')
    out.push({
      type: hasPillar ? 'pillar' : 'emergency',
      start: b.start_m, w: b.end_m - b.start_m,
      left: pct(b.start_m), widthPct: pct(b.end_m - b.start_m),
      label: hasEm && !hasPillar ? '应急' : b.label,
      emTag: hasPillar && hasEm ? '应急' : '',
    })
  }
  for (const [i, p] of (data.value.placements || []).entries()) {
    out.push({
      type: 'stall', start: p.start_m, w: p.width_m,
      left: pct(p.start_m), widthPct: Math.max(pct(p.width_m), 2),
      label: p.vendor_name, color: colors[i % colors.length],
    })
  }
  return out.sort((a, b) => a.start - b.start)
})
</script>
<template>
  <div class="ss-street-wrap">
    <h1>街段分配带</h1>
    <p class="sub">沿街一维开间 · 两端应急带留白、挡柱为竖直阻断，均与引擎同一套区间 · 底部为摊主排队</p>
    <button class="btn" @click="run">按当前登记重新分配</button>
    <div class="ss-band-ruler" v-if="data">
      <span>0 m</span>
      <span>{{ data.segment.name }} · {{ data.segment.width_m }} m · 起点应急 {{ data.start_emergency_m }} m / 终点应急 {{ data.end_emergency_m }} m</span>
      <span>{{ data.segment.width_m }} m</span>
    </div>
    <div class="ss-street-band" v-if="data">
      <div class="ss-street-inner">
        <div
          v-for="(c,i) in cells" :key="i"
          class="ss-band-cell"
          :class="{ 'ss-pillar': c.type === 'pillar', 'ss-emergency': c.type === 'emergency' }"
          :style="{ left: c.left + '%', width: c.widthPct + '%', background: c.type === 'stall' ? c.color : undefined }"
        >
          <span v-if="c.emTag" class="ss-em-tag">{{ c.emTag }}</span>
          {{ c.label }}
        </div>
      </div>
    </div>
    <div class="ss-vendor-queue">
      <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}</strong>
        <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
      </div>
    </div>
    <div class="card" v-if="data">
      <table>
        <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
        <tbody>
          <tr v-for="p in data.placements" :key="p.vendor_id">
            <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
