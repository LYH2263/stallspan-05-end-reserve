<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const drafts = ref<Record<number, { start: string; end: string }>>({})
const error = ref('')
const saving = ref<number | null>(null)
const loaded = ref(false)

function syncDraft(r: any) {
  drafts.value[r.id] = { start: String(r.start_emergency_m ?? 0), end: String(r.end_emergency_m ?? 0) }
}

onMounted(async () => {
  await reload()
  loaded.value = true
})

async function save(r: any) {
  error.value = ''
  const d = drafts.value[r.id]
  const start = Number(d.start)
  const end = Number(d.end)
  // 前端先拦一道：非法提交根本不发，页面与图都停在改前
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < 0
      || start + end >= r.width_m) {
    error.value = `非法值：应急米数须 ≥ 0，且两端之和必须小于街宽 ${r.width_m} m`
    syncDraft(r)  // 整单拒绝，页上不得留新值
    return
  }
  saving.value = r.id
  try {
    // 服务端按提交瞬间的新值落库；400 时库不改，返回后仍以服务端旧值为准
    const updated = await api(`/segments/${r.id}/emergency`, {
      method: 'PUT',
      body: JSON.stringify({ start_emergency_m: start, end_emergency_m: end }),
    })
    Object.assign(r, updated)
    syncDraft(r)
  } catch (e: any) {
    error.value = e?.message || '提交被拒绝，维持改前数值'
    await reload()
  } finally {
    saving.value = null
  }
}

async function reload() {
  rows.value = await api('/segments')
  rows.value.forEach(syncDraft)
}
</script>
<template>
  <h1>街段</h1>
  <p class="sub">沿街可用宽度（米）· 两端应急带登记：起点/终点应急米数，可用开间从带内侧起算</p>
  <p v-if="error" class="badge badge-bad" style="margin-bottom:0.6rem">{{ error }}</p>
  <div class="card">
    <table v-if="loaded">
      <thead><tr><th>街段</th><th>宽度(m)</th><th>起点应急(m)</th><th>终点应急(m)</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.name }}</td>
          <td>{{ r.width_m }}</td>
          <td><input v-model="drafts[r.id].start" type="number" min="0" step="0.5" style="width:90px"></td>
          <td><input v-model="drafts[r.id].end" type="number" min="0" step="0.5" style="width:90px"></td>
          <td>
            <button class="btn" :disabled="saving === r.id" @click="save(r)">
              {{ saving === r.id ? '提交中…' : '登记应急带' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p class="muted" style="margin-bottom:0;font-size:0.78rem">
      非法值（负数或两端之和不小于街宽）整单拒绝；两端均为 0 时与不挖应急带的绿仓口径一致。
    </p>
  </div>
</template>
