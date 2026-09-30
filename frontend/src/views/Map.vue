<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
const vendors = ref<any[]>([])
async function run() { data.value = await api('/allocate/run?segment_id=1', { method: 'POST' }) }
onMounted(async () => {
  vendors.value = await api('/vendors')
  await run()
})
const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']
// 所有图形坐标都取自同一次运行快照（引擎挖带结果）：
// 应急留白、挡柱、摊位起止共用同一套米数，主图不得另算一套。
const cells = computed(() => {
  if (!data.value) return []
  const width = data.value.segment.width_m
  const pct = (m: number) => (m / width) * 100
  const out: any[] = []
  // 两端应急带：米数直接取运行快照中的登记值（与引擎挖空同套）
  const em = data.value.emergency || { start_m: 0, end_m: 0 }
  if (em.start_m > 0)
    out.push({ type: 'emergency', start: 0, w: em.start_m, label: `起点应急 ${em.start_m}m` })
  if (em.end_m > 0)
    out.push({ type: 'emergency', start: width - em.end_m, w: em.end_m, label: `终点应急 ${em.end_m}m` })
  for (const p of data.value.pillars || []) {
    out.push({ type: 'pillar', start: p.position_m - p.thickness_m / 2, w: p.thickness_m, label: p.label || '挡柱' })
  }
  for (const [i, p] of (data.value.placements || []).entries()) {
    out.push({ type: 'stall', start: p.start_m, w: p.width_m, label: p.vendor_name, color: colors[i % colors.length] })
  }
  return out.map(c => ({ ...c, left: pct(c.start), pct: Math.max(pct(c.w), 1.5) }))
})
</script>
<template>
  <div class="ss-street-wrap">
    <h1>街段分配带</h1>
    <p class="sub">沿街一维开间 · 两端为应急留白（摊位起止不得进入）· 挡柱为竖直阻断 · 底部为摊主排队</p>
    <button class="btn" @click="run">重新分配</button>
    <div class="ss-band-ruler" v-if="data">
      <span>{{ (data.emergency?.start_m || 0) > 0 ? `应急 ${data.emergency.start_m}m ▏0 m` : '0 m' }}</span>
      <span>{{ data.segment.name }} · 共 {{ data.segment.width_m }} m · 可用开间从应急带内侧起算</span>
      <span>{{ data.segment.width_m }} m ▕{{ (data.emergency?.end_m || 0) > 0 ? ` 应急 ${data.emergency.end_m}m` : '' }}</span>
    </div>
    <div class="ss-street-band" v-if="data">
      <div class="ss-street-inner ss-street-abs">
        <div
          v-for="(c,i) in cells" :key="i"
          class="ss-band-cell"
          :class="{ 'ss-pillar': c.type === 'pillar', 'ss-emergency': c.type === 'emergency' }"
          :style="{ left: c.left + '%', width: c.pct + '%', background: c.type === 'stall' ? c.color : undefined }"
        >{{ c.type === 'stall' ? c.label : '' }}<span v-if="c.type !== 'stall'" class="ss-zone-label">{{ c.label }}</span></div>
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
